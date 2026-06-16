# BAND-hack

# BandAid — Self-Assembling Incident War Rooms

> When production breaks at 3 AM, engineers shouldn't have to play human router.

BandAid is an autonomous incident response system built on [Band](https://band.ai). When the demo checkout API fails, a Watchdog opens an incident room and recruits an Incident Commander, who dynamically assembles specialists — Log Analyst, Fix Engineer, Reviewer, Compliance Officer, and Scribe — to investigate, patch, review, approve, and document the incident.

A second layer, **Band Orchestrator**, can scaffold, convert, and deploy new Band agents at runtime — including company-aware code-context agents backed by a dependency graph and doc RAG over a GitHub repo.

Built for the **Band of Agents Hackathon** (lablab.ai, June 12–19 2026).

## Architecture

### Incident response (BandAid)

```
Alert → Watchdog → Band Incident Room → Incident Commander
                                              ↓
                         Dynamic recruitment of specialists
                                              ↓
                    Log Analyst → Fix Engineer → Reviewer
                                              ↓
                         Human SRE approval gate (chat)
                                              ↓
                         Scribe → Postmortem + Memory
```

### Agent factory (Band Orchestrator)

```
Band room → Band Orchestrator
                ↓
    create / convert / deploy agents → generated_agents/<slug>_<uuid>/
                ↓
    optional: company context agent (code graph + docs RAG from GitHub)
                ↓
    thenvoi_add_participant → new agent joins the room
```

## Agents

Eight registered agent types. All LLM agents share the same bootstrap (`band.agents.base.create_and_run`) unless noted.

| Agent | Config key | Runtime | Role |
| ----- | ---------- | ------- | ---- |
| Watchdog | `watchdog` | No LLM — `BandAgentClient` + httpx poll loop | Monitors `/health`, opens `INC-*` rooms, @mentions commander |
| Incident Commander | `incident_commander` | `adapter_sdk()` (default: Claude Code CLI) | Classifies, recruits peers, coordinates handoffs |
| Log Analyst | `log_analyst` | LangGraph + Featherless if `FEATHERLESS_API_KEY` set; else `adapter_sdk` fallback | Root-cause analysis via demo-app logs/metrics |
| Fix Engineer | `fix_engineer` | `adapter_sdk()` with `permission_mode=bypassPermissions` | Git/gh tools: branch, patch, PR, merge, restore service |
| Reviewer | `reviewer` | `adapter_sdk()` (default: Claude; set `DEFAULT_ADAPTER_TYPE=codex` for Codex) | Fetches PR diff, posts adversarial review |
| Compliance Officer | `compliance_officer` | LangGraph + AI/ML API if `AIML_API_KEY` set; else `adapter_sdk` fallback | GDPR/DPDP/SOC2 assessment when PII suspected |
| Scribe | `scribe` | `adapter_sdk()` + memory tools | Postmortem + `store_incident_memory` |
| Band Orchestrator | `band_orchestrator` | `adapter_sdk()` + 8 custom tools | Scaffolds/deploys agents into `generated_agents/` |

`DEFAULT_ADAPTER_TYPE` (`claude` \| `codex` \| `gemini`) controls the default SDK adapter for agents that use `adapter_sdk()`. The orchestrator's `generator` and `converter` modules call Gemini directly (`gemini-2.5-flash`) regardless of this setting.

Console entry points (`pyproject.toml`): `bandhack-watchdog`, `bandhack-commander`, `bandhack-log-analyst`, `bandhack-fix-engineer`, `bandhack-reviewer`, `bandhack-compliance`, `bandhack-scribe`. There is no `bandhack-orchestrator` script — run via `python -m agents.band_orchestrator.main` or `scripts/run_all.py --run-band-orchestrator`.

## Band features used

- Runtime agent recruitment (`thenvoi_add_participant`, peer lookup)
- @mention routing for task handoffs
- Human-in-the-loop approval via chat (prompt-driven; see `band/approval.py` helpers)
- Full audit trail (`thenvoi_send_event`)
- Memory API for institutional learning
- Multi-framework orchestration in one room (Claude SDK, Codex, Gemini ADK, LangGraph)

## Quick start

### 1. Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose
- Band account + Human API key
- Claude Code CLI (default adapter) and/or API keys below
- Optional: `FEATHERLESS_API_KEY` (Log Analyst), `AIML_API_KEY` (Compliance), `GITHUB_TOKEN` + `gh` (Fix Engineer PR flow)

### 2. Install

```bash
git clone <your-repo>
cd BAND-hack
cp .env.example .env
cp agent_config.yaml.example agent_config.yaml
uv sync
```

### 3. Start demo app

```bash
cd demo-app
docker compose up --build -d
curl http://localhost:8080/health
```

### 4. Register agents on Band

```bash
# Set BAND_HUMAN_API_KEY in .env first
uv run python scripts/setup_agents.py
# Writes/merges credentials into agent_config.yaml automatically
```

Use `--dry-run` to preview which agents would be registered.

### 5. Start agents

```bash
# Incident war room (7 agents)
uv run python scripts/run_all.py

# Also start Band Orchestrator
uv run python scripts/run_all.py --run-band-orchestrator

# Orchestrator only (agent factory demos)
uv run python scripts/run_all.py --run-only-band-orc
```

Other flags: `--skip-watchdog`, `--skip-compliance`, `--skip-reviewer`.

### 6. Run a demo scenario

```bash
# Pool exhaustion (simple outage)
uv run python scripts/demo.py outage

# PII leak (triggers Compliance Officer)
uv run python scripts/demo.py pii

# Bad config deploy
uv run python scripts/demo.py deploy

# Clear faults
uv run python scripts/demo.py --clear
```

Open the Band UI to watch the war room assemble in real time.

## Demo flow

1. `scripts/demo.py` POSTs a fault to `demo-app` `/chaos/{fault}`
2. Watchdog detects unhealthy `/health` and creates an `INC-*` room
3. Incident Commander classifies and recruits Log Analyst
4. Log Analyst fetches logs/metrics, posts root-cause hypothesis
5. Commander recruits Fix Engineer → opens PR via `gh`
6. Reviewer critiques PR
7. Commander waits for human SRE — type **approve** in Band UI
8. Fix Engineer merges and clears chaos (`mergepr` calls `clear_chaos`)
9. Scribe generates postmortem and stores memory

## Band Orchestrator tools

| Tool | What it does |
| ---- | ------------ |
| `createbandagent` | Scaffold a new agent from a description → `generated_agents/<slug>_<uuid>/` → spawn subprocess |
| `convertagent` | Wrap existing agent code as Band-compatible (`band_integration.py`) → spawn |
| `listgeneratedagents` | List running generated-agent subprocesses |
| `stopgeneratedagent` | Terminate a subprocess (files remain on disk) |
| `publishagent` | Open a GitHub PR with generated agent code (`AGENTS_REPO` or `DEMO_APP_REPO`) |
| `createcompanycontextagent` | Copy company-context template into `generated_agents/` |
| `buildcompanycontext` | Clone a GitHub repo; build code graph + docs RAG indexes |
| `deploycompanycontextagent` | Spawn the company-context agent |

After any deploy, the orchestrator prompt requires calling `thenvoi_add_participant` to bring the new agent into the room.

## Demo app

FastAPI checkout API on port **8080** (Docker Compose: Postgres + API).

| Endpoint | Purpose |
| -------- | ------- |
| `GET /health` | Returns unhealthy when chaos is active |
| `GET /metrics` | Prometheus-style counters |
| `GET /logs` | Structured log buffer |
| `POST /checkout` | Checkout flow (fault behaviors apply) |
| `GET /chaos/status` | Active fault state |
| `POST /chaos/clear` | Clear all faults |
| `POST /chaos/{fault}` | Activate `pool_exhaustion`, `pii_leak`, or `bad_config` |

`pool_exhaustion` is simulated via health flags (does not actually exhaust the DB pool).

## Project structure

```
band/                    Shared config, Band REST client, tools, prompts, SDK adapters
agents/                  One process per agent (8 registered types)
  band_orchestrator/     Meta-agent: generator, converter, company-context template
  commander/             Incident Commander
  compliance/            Compliance Officer
  fix_engineer/          Fix Engineer
  log_analyst/           Log Analyst
  reviewer/              Reviewer
  scribe/                Scribe
  watchdog/              Watchdog (no LLM)
demo-app/                FastAPI + Postgres target with /chaos endpoints
generated_agents/        Runtime output from orchestrator (gitignored)
scripts/                 setup_agents.py, run_all.py, demo.py
examples/                Sample agent for convert-agent demos
tests/                   Unit tests
```

See [AGENTS.md](AGENTS.md) for a detailed guide aimed at contributors and coding agents.

## Environment variables

| Variable | Purpose |
| -------- | ------- |
| `BAND_HUMAN_API_KEY` | Register agents via Human API |
| `BAND_REST_URL`, `BAND_WS_URL` | Band platform endpoints |
| `DEMO_APP_URL` | Target for watchdog and analyst tools (default `http://localhost:8080`) |
| `DEMO_APP_REPO` | GitHub repo URL for Fix Engineer PR flow |
| `GITHUB_TOKEN` | Auth for `gh` / git operations |
| `AGENTS_REPO` | Target repo for `publishagent` PRs (falls back to `DEMO_APP_REPO`) |
| `DEFAULT_ADAPTER_TYPE` | `claude` (default), `codex`, or `gemini` |
| `CLAUDE_CODE_MODEL` | Claude Code CLI model (`sonnet`, `opus`, `haiku`) |
| `FEATHERLESS_API_KEY` | Enable LangGraph + Featherless for Log Analyst |
| `AIML_API_KEY` | Enable LangGraph + AI/ML API for Compliance Officer |
| `WATCHDOG_*` | Poll interval, failure threshold, timeouts |

Full list in [`.env.example`](.env.example). Agent credentials live in `agent_config.yaml` (see `agent_config.yaml.example`).

## Hackathon submission

- **Track**: Regulated & High-Stakes Workflows (Track 3) + Software Development (Track 2)
- **Partner tech**: Featherless (Log Analyst), AI/ML API (Compliance Officer)
- **License**: MIT

### Submission checklist

- [ ] Public GitHub repo (this repo)
- [ ] Cover image + slide deck
- [ ] 3–5 min demo video showing Band room collaboration
- [ ] Application URL: demo-app on localhost or deployed instance
- [ ] lablab.ai submission form

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
