# BAND-hack — A Band of Agents for Your Codebase

A team ("band") of [Band](https://band.ai) agents that manage a software project end to end:

1. **Build features** — ask the team to implement a change; they plan, code, review, get your approval, and prepare a PR.
2. **Resolve incidents fast** — when your hosted app's health fails (e.g. at 3 AM), a watchdog automatically spins up an incident room and the team drives the fix.
3. **Understand your codebase** — a documentation agent maintains a dependency graph, a docs RAG, and a commit-history graph you can query any time.

Everything is bootstrapped by a single **Band Orchestrator** agent. You run the orchestrator, tell it `make company agents`, and it deploys the whole roster for your repo.

All agents use the **Gemini** SDK adapter by default.

---

## Architecture

```
                            ┌───────────────────────┐
   you (Band chat)  ───────▶│   Band Orchestrator   │   "make company agents"
                            └───────────┬───────────┘
                                        │ deploys + builds context
        ┌───────────────────────────────┼────────────────────────────────┐
        ▼                ▼               ▼            ▼          ▼          ▼
   ┌─────────┐    ┌───────────────┐ ┌─────────┐ ┌────────┐ ┌───────┐ ┌──────────┐
   │ watchdog│    │ documentation │ │commander│ │planner │ │ coder │ │ reviewer │
   │ (no LLM)│    │     agent     │ │         │ │        │ │       │ │          │
   └────┬────┘    └───────┬───────┘ └────┬────┘ └───┬────┘ └───┬───┘ └────┬─────┘
        │ polls /health   │ graph+RAG     │ coordinates the two flows below │
        ▼                 │ commit graph  │                                 │
   hosted app  ◀──────────┘               ▼                                 ▼

INCIDENT FLOW (automatic):
  watchdog detects unhealthy /health → opens incident room, recruits commander+planner+documentation_agent
  → commander → planner (consults documentation_agent) → coder (reads real files, applies minimal fix,
    verifies health) → reviewer (reviews real local diff) → commander asks YOU to approve
  → coder finalizes PR → documentation_agent refreshes graph → INCIDENT_RESOLVED

FEATURE FLOW (you start it):
  you open a room with commander+planner+coder+reviewer+documentation_agent → @commander "build X"
  → planner (consults documentation_agent) → coder → reviewer → commander asks YOU to approve
  → coder opens PR → documentation_agent refreshes graph → FEATURE_DONE
```

### Agent roster

| Agent                | LLM     | Role                                                                         |
| -------------------- | ------- | ---------------------------------------------------------------------------- |
| `watchdog`           | none    | Polls the hosted app `/health`; opens an incident room on failure            |
| `documentation_agent`| Gemini  | Code dependency graph (code2flow viz + queryable JSON), docs RAG, commit graph |
| `commander`          | Gemini  | Coordinates the workflow; single-owner handoffs; human approval gate         |
| `planner`            | Gemini  | Turns a request/incident into a bounded plan using documentation context     |
| `coder`              | Gemini  | Reads real files, applies the fix, verifies health, prepares/opens the PR    |
| `reviewer`           | Gemini  | Reviews the real diff and returns APPROVE / REQUEST_CHANGES / ESCALATE       |

The **Band Orchestrator** (`agents/band_orchestrator`) is the only agent you start manually for setup; it deploys the six above.

---

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- A Band account with agent credentials (6 agents + 1 orchestrator)
- `GEMINI_API_KEY` (used by all LLM agents)
- Optional: `GITHUB_TOKEN` + GitHub CLI (`gh`) — only needed to open *real* PRs. Without it the
  team still clones, edits, reviews the local diff, and gives you a compare URL.
- Docker (only if you want to run the demo app's Postgres via compose; a plain uvicorn run also works)

## Install

```bash
git clone <your-repo>
cd BAND-hack
cp .env.example .env            # fill in GEMINI_API_KEY etc.
cp agent_config.yaml.example agent_config.yaml   # fill in Band agent IDs + API keys
uv sync
```

Key `.env` values:

```bash
GEMINI_API_KEY=...
DEFAULT_ADAPTER_TYPE=gemini
HOSTED_APP_URL=https://band-of-agents-demo.vercel.app   # health/logs target; omit for local :3000
DEMO_APP_REPO=https://github.com/Ajitesh-jam/band-of-agents-demo.git   # repo the coder/docs use
COMPANY_REPO_URL=https://github.com/Ajitesh-jam/band-of-agents-demo.git
GITHUB_TOKEN=                            # optional; leave empty for local/no-PR mode
```

### Shared workspace (`.workspace/repo`)

Planner, coder, reviewer, github_agent, and documentation_agent all use **one git clone** at
`.workspace/repo` (from `DEMO_APP_REPO` or `COMPANY_REPO_URL`). The documentation agent builds
its code graph from that same directory — not a separate temp clone.

If you change `DEMO_APP_REPO` to point at a different GitHub repo, clear stale clones first:

```bash
rm -rf .workspace/demo-app .workspace/repo
uv run python agents/documentation_agent/scripts/build_code_graph.py \
  --github-url "$DEMO_APP_REPO" --agent-root agents/documentation_agent
```

`clone_repo` automatically re-clones when the configured URL no longer matches `git remote origin`.

---

## How to run

### 1. Start the demo app (the "hosted app" the watchdog watches)

Simplest (no Docker needed):

```bash
cd demo-app
uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
curl http://localhost:8080/health      # {"status":"healthy",...}
```

Or with Docker (includes Postgres):

```bash
cd demo-app
docker compose -f docker-compose.yml up --build
```

### 2. Make the company agents (one-time, via the orchestrator)

Start only the orchestrator:

```bash
uv run python scripts/run_all.py --run-only-band-orc
# or: uv run python -m agents.band_orchestrator.main
```

In the Band UI, open a chat with the orchestrator. It posts a **startup brief** describing what it
can do. Then send:

```
make company agents for repo https://github.com/Ajitesh-jam/band-hack-demo.git
hosted at http://localhost:8080
```

The orchestrator will:
- persist the repo/hosted URLs (and token if provided) to `.env`,
- ensure `agent_config.yaml` exists,
- copy the six agent templates into `agents/`,
- build the documentation agent's **code graph** (code2flow `.gv`/`.svg` + queryable `code_graph.json`),
  **docs RAG** (`docs_index.json` from anything you drop in `agents/documentation_agent/docs/`), and
  **commit graph** (`commit_graph.json`),
- deploy all six agents and add them to the room.

> The graph builder uses **code2flow** for visualization (not "graphify", which is not a real
> package) plus an AST/import scan for the queryable JSON graph. If a repo/token is missing it still
> builds the best graph it can from local files.

### 3. Run the standing team (for day-to-day incident + feature flows)

Once the agents exist in `agents/`, you normally just run the six-agent roster directly:

```bash
uv run python scripts/run_all.py
```

Flags: `--run-band-orchestrator` (also start orchestrator), `--run-only-band-orc`,
`--skip-watchdog`, `--skip-reviewer`.

---

## How to test

### Test A — Incident flow (automatic)

With the demo app + roster running, inject a fault. The watchdog polls `/health`, sees it fail,
and opens an incident room.

```bash
# convenience script
uv run python scripts/demo.py outage      # pool_exhaustion (server unhealthy)
uv run python scripts/demo.py pii         # pii_leak
uv run python scripts/demo.py deploy      # bad_config (elevated error rate)
uv run python scripts/demo.py --clear     # clear all faults

# or raw HTTP
curl -X POST http://localhost:8080/chaos/pool_exhaustion
curl http://localhost:8080/health
curl -X POST http://localhost:8080/chaos/clear
```

Then watch the incident room in the Band UI. You should see, in order:
`watchdog ALERT → commander acknowledges → planner asks documentation_agent → plan → coder applies
fix + verifies health → reviewer APPROVE → commander asks you to approve → coder PR step →
INCIDENT_RESOLVED`. Type **approve** in the room when the commander asks.

### Test B — Feature flow (you start it)

In the Band UI, create a room and add `commander`, `planner`, `coder`, `reviewer`,
`documentation_agent`. Then mention the commander:

```
@commander add a /version endpoint to the checkout API that returns the app version
```

Same plan → code → review → approval → PR sequence.

### Test C — Ask the documentation agent

In any room with the documentation agent:

```
@documentation_agent what does app/database.py depend on, and what recent commits touched it?
```

### Unit tests

```bash
uv run --with pytest --with pytest-asyncio python -m pytest -q
```

---

## Loop prevention

Multi-agent rooms can echo-storm (agents repeating plans/acks forever). This project prevents that with:

- **Strict prompt discipline** (`band/prompts.py`): no acknowledgement-only messages, hand each
  artifact to the next owner *exactly once*, mention only the single next owner, and explicit
  **terminal states** (`INCIDENT_RESOLVED`, `FEATURE_DONE`, `ESCALATE`) after which agents stop.
- **Bounded revisions**: planner ≤ 2 revisions, reviewer ≤ 2 `REQUEST_CHANGES`, coder ≤ 1 re-plan
  per blocker, then `ESCALATE`.
- **Completable tooling** (the real fix for the loop): the chain can actually *finish*. The reviewer
  reviews a real **local git diff** (no `gh` needed), the coder has `read_file`/`list_repo_files`
  (so it edits real files instead of hallucinating), and `openpr` degrades to a **manual compare
  URL** when no `GITHUB_TOKEN` is set instead of failing forever.

## Reused-credential handle aliases

If you reuse Band credentials that were registered under older names, teammates may appear under
legacy handles (`incident-commander`, `log-analyst`, `fix-engineer`, `scribe`, `watch-dog`). The
agent prompts include a role↔handle alias map so coordination still resolves the right teammate.
To avoid this entirely, register fresh Band agents named `commander/planner/coder/documentation_agent/reviewer/watchdog`.

---

## Project structure

```
band/                     Shared config, Band REST client, prompts, tools (github_ops, demo_app)
  agents/base.py          adapter_sdk(), create_and_run(), startup-brief plumbing
  agents/sdk/gemini_sdk.py Gemini adapter + proactive startup brief
  prompts.py              All agent system prompts + loop guard + team roster
  tools/github_ops.py     clone/read/list/write/commit/diff/PR (gh-optional, token-optional)
agents/                   One folder per agent (process entry points)
  band_orchestrator/      Orchestrator + agent_core (company_agent.py, process_runner.py) + templates/
  watchdog/ documentation_agent/ commander/ planner/ coder/ reviewer/
demo-app/                 FastAPI checkout API with /chaos fault injection (the target app)
scripts/                  run_all.py, demo.py, setup_agents.py
tests/                    Unit tests
logs/                     Runtime logs (orchestrator, roster)
```

## How it works (key modules)

- **Startup brief** — `band/agents/sdk/gemini_sdk.py` posts the orchestrator's capability brief the
  first time a *new* room bootstraps (a short grace window suppresses spamming pre-existing rooms),
  mentioning the other participants. Wired in `agents/band_orchestrator/main.py`.
- **make company agents** — `agents/band_orchestrator/agent_core/company_agent.py::deploy_company_roster`
  persists config, copies templates into `agents/`, runs the documentation builds, and returns agent
  metadata; `main.py` spawns each as a tracked subprocess via `process_runner.py`.
- **Documentation builds** — `agents/documentation_agent/scripts/build_code_graph.py` clones the repo
  to a temp dir, runs code2flow for `.gv`/`.svg`, builds the queryable `code_graph.json`, extracts the
  commit graph from `git log`, then deletes the temp clone. `build_docs_rag.py` embeds `docs/`.
- **Incident detection** — `agents/watchdog/agent_core/helper.py::monitor_loop` polls `/health`,
  classifies the failure, and `open_incident_room` recruits commander + planner + documentation_agent.

## License

MIT — see [LICENSE](LICENSE).
