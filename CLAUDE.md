# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**BandAid** — Self-Assembling Incident War Rooms. An autonomous incident response system built on the [Band](https://band.ai) platform. When production breaks, a Watchdog opens an incident room and recruits an Incident Commander, who dynamically assembles specialist agents to investigate, patch, review, approve, and document the incident.

Built for the **Band of Agents Hackathon** (lablab.ai, June 12–2026).

## Architecture

```
Alert → Watchdog → Band Incident Room → Incident Commander
                                              ↓
                         Dynamic recruitment of specialists
                                              ↓
                    Log Analyst → Fix Engineer → Reviewer
                                              ↓
                         Human SRE approval gate
                                              ↓
                         Scribe → Postmortem + Memory
```

### Key Design Principles

- **Multi-framework orchestration**: Each agent uses a different LLM framework unified by the Band SDK (`thenvoi`), demonstrating Band's polyglot agent runtime.
- **Agent recruitment model**: Specialists are dynamically added to rooms via `thenvoi_add_participant` — the Commander peers discover and recruit them.
- **Human-in-the-loop**: SRE approval is required before merge/deploy. Agents detect approval keywords (`approve`, `LGTM`, `ship it`) via regex patterns in `band/approval.py`.
- **@mention routing**: Task handoffs between agents happen through Band's @mention system, not direct function calls.

### Agent Roster

| Agent | Framework | Role |
|---|---|---|
| Watchdog | Python SDK (no LLM) | Monitors health, opens incident rooms |
| Incident Commander | Claude Code CLI (`claude_agent`) | Classifies, recruits, coordinates |
| Log Analyst | LangGraph + Featherless / Claude CLI fallback | Root-cause analysis from logs/metrics |
| Fix Engineer | Claude Code CLI w/ custom tools | Patches code, opens GitHub PRs |
| Reviewer | Claude Code CLI w/ custom tools | Cross-model PR review |
| Compliance Officer | LangGraph + AI/ML API / Claude CLI fallback | GDPR/DPDP assessment (conditional) |
| Scribe | Claude Code CLI w/ custom tools | Postmortem + Band Memory API |
| Band Orchestrator | Gemini (default) | Builds and deploys new Band agents on demand |

## Directory Structure

```
band/                          Shared infrastructure
  __init__.py
  agents/
    base.py                    bootstrap_env(), load_creds(), adapter_sdk(), create_and_run()
    claude_sdk.py              claude_agent() — local Claude CLI adapter (no API billing)
    sdk/claude_sdk.py          (alternate path — same)
    sdk/codex_sdk.py           Codex CLI adapter
    sdk/gemini_sdk.py          Gemini CLI adapter
  approval.py                  Approval/rejection regex patterns, SRE_APPROVAL_PROMPT
  client.py                    BandHumanClient + BandAgentClient (REST API wrappers)
  config.py                    Settings (pydantic_settings, loads .env)
  prompts.py                   All agent system prompt strings
  registry.py                  AgentCredentials, load/save agent_config.yaml, AGENT_DEFINITIONS
  tools/
    demo_app.py                fetch_health, fetch_metrics, fetch_logs, chaos ops
    github_ops.py              clone_or_pull, create_branch, write_file, commit_push, open_pr, merge_pr, publish_agent_pr
    memory_ops.py              recall_similar_incidents, store_incident_memory, fetch_room_context

agents/                        One subdirectory per agent
  watchdog/                    No-LLM health monitor
    main.py → cli()            Entry point: uv run python -m agents.watchdog.main
    agent_core/helper.py       check_health(), open_incident_room(), monitor_loop()
  commander/                   Incident Commander (Claude Code CLI)
    main.py → cli()
  log_analyst/                 Log Analyst (LangGraph + Featherless / Claude CLI)
    main.py → cli()
    agent_core/helper.py       _featherless_configured(), _make_langchain_tools(), _make_claude_tools()
    agent_core/schema.py       Pydantic input models (FetchLogsInput, etc.)
  fix_engineer/                Fix Engineer (Claude Code CLI + GitHub tools)
    main.py → cli()
    agent_core/schema.py       CloneRepoInput, CreateBranchInput, OpenPRInput, MergePRInput, etc.
  reviewer/                    Reviewer (Claude Code CLI + fetch PR diff)
    main.py → cli()
    agent_core/schema.py       FetchPRDiffInput
  compliance/                  Compliance Officer (LangGraph + AI/ML API / Claude CLI)
    main.py → cli()
  scribe/                      Scribe (Claude Code CLI + memory tools)
    main.py → cli()
    agent_core/schema.py       FetchContextInput, StoreMemoryInput
  band_orchestrator/           Agent builder/deployer (Gemini default)
    main.py → cli()
    agent_core/
      schema.py                Pydantic input models for orchestrator tools
      generator.py             Scaffolds new agent folders under generated_agents/
      converter.py             Converts existing codebases via band_integration.py
      process_runner.py        ProcessManager — spawns/manages agent subprocesses
      retriever.py             Context retrieval for code conversion

demo-app/                      FastAPI + Postgres checkout-api (incident target)
  app/
    main.py                    REST endpoints: /health, /metrics, /logs, /checkout, /chaos/*
    chaos.py                   FaultType enum, ChaosState dataclass (pool_exhaustion, pii_leak, bad_config)
    database.py                SQLAlchemy models (Product, Order), session_scope
    log_buffer.py              In-memory ring buffer for structured logs
    logging_config.py          Logging setup
  docker-compose.yml           db (postgres:16-alpine) + api service

scripts/
  setup_agents.py              Registers agents on Band via Human API, saves to agent_config.yaml
  run_all.py                   Starts all agent processes (subprocess.Popen per agent)
  demo.py                      Injects faults: outage, pii, deploy; or --clear

tests/
  conftest.py                  Adds project root + demo-app to sys.path
  test_watchdog.py             Peer lookup + failure classification tests
  test_approval.py             Approval/rejection regex tests
  test_demo_app_tools.py       Demo app tool tests
  test_github_ops.py           GitHub operation tests
  test_registry.py             Agent config registry tests
```

## Environment Configuration

Copy `.env.example` → `.env` and fill in:
- `BAND_HUMAN_API_KEY` — Band platform human API key
- `DEMO_APP_URL` — default `http://localhost:8080`
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FEATHERLESS_API_KEY`, `AIML_API_KEY` — LLM provider keys
- `GITHUB_TOKEN` — for real PR flow (optional)
- `CLAUDE_CODE_MODEL` — `sonnet` (default), `opus`, or `haiku`

Agent credentials after registration go in `agent_config.yaml` (see `agent_config.yaml.example`).

## Common Development Commands

```bash
# Install dependencies
uv sync                          # production
uv sync --extra dev              # include pytest, ruff

# Lint
uv run ruff check .

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_watchdog.py

# Run a single test
uv run pytest tests/test_watchdog.py::test_find_peer_id_by_handle

# Start demo app (requires Docker)
cd demo-app && docker compose up --build -d
curl http://localhost:8080/health

# Register agents on Band (set BAND_HUMAN_API_KEY first)
uv run python scripts/setup_agents.py

# Start all agents
uv run python scripts/run_all.py
uv run python scripts/run_all.py --skip-compliance  # skip compliance officer

# Run demo scenarios
uv run python scripts/demo.py outage                # pool exhaustion
uv run python scripts/demo.py pii                   # PII leak (triggers compliance)
uv run python scripts/demo.py deploy                # bad config
uv run python scripts/demo.py --clear               # clear all faults
```

## Agent SDK Pattern

Every agent follows the same bootstrap pattern:

```python
from band.agents.base import create_and_run, adapter_sdk
from band.prompts import <AGENT>_PROMPT

def build_adapter():
    return adapter_sdk(<AGENT>_PROMPT, enable_memory=<bool>)

def cli():
    create_and_run(build_adapter(), "<agent_config_key>", "<Label>")

if __name__ == "__main__":
    cli()
```

- `adapter_sdk()` selects the adapter via `settings.default_adapter_type` (default: `"claude"`), or per-agent override. Supports `"claude"`, `"codex"`, `"gemini"`.
- `create_and_run()` loads credentials from `agent_config.yaml`, creates a `thenvoi.Agent`, and runs it.
- Agents with custom tools pass `additional_tools` as `(PydanticInputModel, handler)` tuples.

## Watchdog Incident Flow

The Watchdog (`agents/watchdog/agent_core/helper.py`) runs a polling loop:
1. Polls `/health` every `WATCHDOG_POLL_INTERVAL_S` (default 5s)
2. On `WATCHDOG_FAILURE_THRESHOLD` (default 2) consecutive failures, opens an incident room via `BandAgentClient.create_chat()`
3. Finds the commander among peers via `list_peers()` + handle matching
4. Adds commander as participant, sends alert message with `@mention`
5. On recovery, sends resolution event and clears `_active_incident`

## Custom Tools Pattern

Fix Engineer and Reviewer use typed custom tools instead of shell access:

- Fix Engineer: `get_repo_info`, `clone_repo`, `createbranch`, `writefile`, `commitpush`, `openpr`, `mergepr`, `restore_service`, `fetch_health`
- Reviewer: `fetch_pr_diff`
- Scribe: `fetch_room_context`, `store_incident_memory`

These map to `band/tools/github_ops.py` and `band/tools/demo_app.py` functions.

## Band Orchestrator

The Band Orchestrator (`agents/band_orchestrator/`) can create or convert agents:

- **Create**: `generator.create_agent()` scaffolds `generated_agents/<slug>_<uuid8>/` with `main.py`, `base.py`, `agent_config.yaml`, `agent_core/prompt.py`, `agent_core/tools.py`. Uses Gemini to generate tool code.
- **Convert**: `converter.convert_agent()` reads an existing codebase, uses Gemini to write `band_integration.py` into the folder, with sandbox validation and auto-repair.
- **Deploy**: `process_manager.spawn()` launches agents as subprocesses with tracked PIDs, log files, and cleanup on exit.

## Demo Scenarios

Three fault types injected via `/chaos/<fault>`:
- `pool_exhaustion` — Returns unhealthy /health response
- `pii_leak` — Checkout leaks PII into error logs (triggers Compliance Officer)
- `bad_config` — 85% error rate on checkout

Clear with `POST /chaos/clear` (also triggered automatically by `merge_pull_request`).

## Important Notes

- `agent_config.yaml` contains API keys — it is gitignored. Never commit it.
- The `band/agents/sdk/` directory contains adapter files at `band/agents/sdk/claude_sdk.py` and `band/agents/claude_sdk.py` — both exist; imports in agent code use the path matching the import site.
- Tests add both project root and `demo-app/` to `sys.path` to resolve both `band.*` and `app.*` imports.
