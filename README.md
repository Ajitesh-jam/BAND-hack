# BAND-hack

# Orchestrator-Led Autonomous Dev Team

> Band Orchestrator is the highest-authority agent that spawns and manages a right-sized engineering team on demand.

When demo-app fails or a human requests a feature, the Orchestrator assembles specialists in a single Band room: **Company Agent → Planner (Opus) → Coder (Claude) → Reviewer (Codex) → PR → human approve → Merger**.

Built for the **Band of Agents Hackathon** (lablab.ai, June 12–19 2026).

## Architecture

```
WatchDog alert ──► Band Orchestrator (spine)
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
   Company Agent    Planner       WatchDog
   (graph + RAG)   (Opus plan)    (persistent)
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
         planner-alpha        planner-beta
         (large repos only)
                        │
                        ▼
              Coder → Reviewer → PR
                        │
              human types "approve"
                        ▼
                    Merger → chaos clear
```

### Persistent agents (started at install)

| Agent | Config key | Brain | Role |
| ----- | ---------- | ----- | ---- |
| Band Orchestrator | `band_orchestrator` | Claude sonnet | Spawns/recruits team; gates merge on human approval |
| Company Agent | `company_agent` | Graphify + RAG + Claude | Code graph (`graphify`) and docs over `demo-app` |
| Watchdog | `watchdog` | None | Polls `/health`; alerts orchestrator on failure |

### Per-task agents (spawned on demand)

| Agent | Config key | Brain | Role |
| ----- | ---------- | ----- | ---- |
| Planner | `planner` | Claude opus | Structured plan; may request alpha/beta for large repos |
| Planner Alpha/Beta | `planner_alpha`, `planner_beta` | Claude opus | Partition plans when file count exceeds threshold |
| Coder | `coder` | Claude sonnet or OpenCode | Local git edits against `demo-app` |
| Reviewer | `reviewer` | Codex | Branch diff review; opens PR when sound |
| Merger | `merger` | Tool-only | Merges PR after human `approve`; clears chaos |

## Quick start

### Prerequisites

- Python 3.11+, [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose
- Band account + Human API key
- Claude Code CLI (orchestrator, planner, company agent) or OpenCode server for coder
- Codex CLI (reviewer)
- Optional: `GITHUB_TOKEN` + `gh` for real PRs (local mode works without)

### Install

```bash
git clone <your-repo>
cd BAND-hack
cp .env.example .env
cp agent_config.yaml.example agent_config.yaml
uv sync
```

### Start demo app

```bash
cd demo-app
docker compose up --build -d
curl http://localhost:8080/health
```

### Register agents

```bash
# Set BAND_HUMAN_API_KEY in .env
uv run python scripts/setup_agents.py
```

### Start the orchestrator

```bash
uv run python scripts/run_all.py
```

The orchestrator bootstraps on startup: `build_context` (graphify + docs RAG), then deploys `company_agent` and `watchdog`. Per-task agents are spawned on demand inside Band rooms.

### Trigger an outage (Flow A)

```bash
uv run python scripts/demo.py outage
```

Expected in Band UI:

1. Watchdog opens a room and @mentions **Band Orchestrator**
2. Orchestrator deploys Planner; Planner consults Company Agent and emits a plan
3. Orchestrator deploys Coder → branch + commit on `demo-app`
4. Orchestrator deploys Reviewer → opens PR (simulated if `DEMO_APP_REPO` empty)
5. Orchestrator asks for approval — type **`approve`** in the room
6. Orchestrator deploys Merger → merge + chaos clear → Watchdog reports healthy

### Request a feature (Flow B)

In a Band room, `@band-orchestrator add a /readiness endpoint to demo-app` — same pipeline, no chaos injection.

## Orchestrator tools

| Tool | What it does |
| ---- | ------------ |
| `deploy_agent` | Spawn `company_agent`, `watchdog`, `planner`, `coder`, `reviewer`, or `merger` |
| `list_agents` | List running subprocesses |
| `build_context` | Rebuild graphify graph + docs index (deterministic) |
| `get_context_paths` | Return graph/docs paths for planner handoff |

After every deploy, call `thenvoi_add_participant` with the returned `agent_id`.

## Configuration

| Variable | Purpose |
| -------- | ------- |
| `ORCHESTRATOR_MODEL`, `PLANNER_MODEL`, `CODER_MODEL` | Per-role Claude models |
| `CODER_ADAPTER` | `claude` (default) or `opencode` when Claude is rate-limited |
| `REVIEWER_ADAPTER` | `codex` (default) |
| `OPENCODE_URL` | OpenCode server (default `http://127.0.0.1:4096`) |
| `BIG_REPO_FILE_THRESHOLD` | Planner spawns alpha/beta above this file count (default 150) |
| `REVIEW_MAX_ROUNDS` | Bounded review loop (default 3) |
| `DEMO_APP_REPO` | GitHub URL for real PRs; empty = local mode |
| `GITHUB_TOKEN` | Auth for `gh` / git |

With `DEMO_APP_REPO` empty, Coder edits in-repo `demo-app/` directly and PR/merge are simulated (merge still clears chaos).

## Project structure

```
band/                    Shared config, client, tools, prompts, SDK adapters
agents/
  band_orchestrator/     Spine + process_runner + company-context template
  company_agent/         Persistent code graph + docs RAG
  watchdog/              Health monitor (no LLM)
  planner/               Opus planning (+ alpha/beta via env)
  coder/                 Claude local edits
  reviewer/              Codex review + PR
  merger/                Post-approval merge
demo-app/                FastAPI target with /chaos endpoints
scripts/                 setup_agents.py, run_all.py, demo.py
tests/
```

See [AGENTS.md](AGENTS.md) for contributor details.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
