# AGENTS.md

Guide for coding agents working on **BAND-hack** (`bandhack`). Orchestrator-led autonomous dev team on Band.

## Architecture

```
WatchDog / human feature request
        ↓
Band Orchestrator (spine — only deployer)
        ↓
Company Agent (graphify + docs RAG) → Planner (Opus) → Coder (Claude/OpenCode) → Reviewer (Codex) → PR → human approve → Merger
```

**Persistent (orchestrator bootstraps at startup):** `company_agent`, `watchdog`  
**Per-task (orchestrator spawns on demand):** `planner`, `planner_alpha`, `planner_beta`, `coder`, `reviewer`, `merger`

`scripts/run_all.py` starts **only** the orchestrator — no double-spawn.

## Repository map

```
band/           Shared library (`band`)
  agents/base.py  adapter_sdk, create_and_run
  agents/sdk/     claude_sdk, codex_sdk, opencode_sdk, gemini_sdk
  tools/          github_ops, graphify_ops, demo_app
  registry.py     AGENT_DEFINITIONS (9 keys)
  prompts.py      Per-role system prompts
agents/
  band_orchestrator/  Spine + process_runner + context_engine
  company_agent/      Graphify code graph + docs RAG
  watchdog/           Health monitor → alerts orchestrator
  planner/            Opus planning (+ alpha/beta partitions)
  coder/              Local git edits (claude or opencode adapter)
  reviewer/           Codex review + open PR
  merger/             Merge after human approval
demo-app/         Target FastAPI app (chaos injection via scripts/demo.py)
scripts/          setup_agents.py, run_all.py, demo.py
```

## Agent bootstrap pattern

```python
from band.agents.base import adapter_sdk, create_and_run
from band.prompts import SOME_PROMPT

def build_adapter():
    return adapter_sdk(SOME_PROMPT, adapter_type=..., model=..., additional_tools=[...])

def cli() -> None:
    create_and_run(build_adapter(), "config_key", "Human Label")
```

## Registered agents

| Config key | Band name | Module |
| ---------- | --------- | ------ |
| `band_orchestrator` | band-orchestrator | `agents.band_orchestrator.main` |
| `company_agent` | company-agent | `agents.company_agent.main` |
| `watchdog` | watchdog | `agents.watchdog.main` |
| `planner` | planner | `agents.planner.main` |
| `planner_alpha` | planner-alpha | `agents.planner.main` |
| `planner_beta` | planner-beta | `agents.planner.main` |
| `coder` | coder | `agents.coder.main` |
| `reviewer` | reviewer | `agents.reviewer.main` |
| `merger` | merger | `agents.merger.main` |

Register: `uv run python scripts/setup_agents.py`

## Orchestrator tools

| Tool | Purpose |
| ---- | ------- |
| `deploy_agent` | Spawn role subprocess + return `agent_id` for `thenvoi_add_participant` |
| `list_agents` | Running PIDs |
| `stop_agent` | Kill per-task agent after merge |
| `build_context` | `graphify update` + docs RAG (deterministic) |
| `get_context_paths` | Hand graph/docs paths to planner |

## Company context

- **Code graph:** [graphify](https://github.com/graphify) CLI → `demo-app/graphify-out/`
- **Docs RAG:** `agents/company_agent/docs/` → `data/docs_index.json`
- Rebuilt at orchestrator startup and after merge via `build_context`

## Coder adapter

Set `CODER_ADAPTER=opencode` and run `opencode serve` when Claude Code is rate-limited.

## Common commands

```bash
uv sync
uv run python scripts/setup_agents.py
uv run python scripts/run_all.py          # orchestrator only
uv run python scripts/demo.py outage      # inject chaos
uv run pytest && uv run ruff check .
graphify update .                         # refresh knowledge graph after code changes
```

## Environment

See `.env.example` for `ORCHESTRATOR_*`, `PLANNER_*`, `CODER_*`, `REVIEWER_ADAPTER`, `OPENCODE_*`, `BIG_REPO_FILE_THRESHOLD`, `REVIEW_MAX_ROUNDS`.

Local mode (`DEMO_APP_REPO` empty): coder edits in-repo `demo-app/`; PR/merge simulated; merge clears chaos.
