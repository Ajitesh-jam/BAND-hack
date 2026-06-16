# AGENTS.md

Guide for coding agents and contributors working on **BAND-hack** (package name: `bandhack`). This file reflects the actual codebase, not aspirational README claims.

## What this repo is

Two systems in one monorepo:

1. **BandAid** — Fixed incident-response agents that detect demo-app failures, open Band rooms, investigate, patch via GitHub PRs, get human approval, and write postmortems.
2. **Band Orchestrator** — Meta-agent that scaffolds, converts, deploys, and publishes *new* Band agents at runtime under `generated_agents/`.

## Repository map

```
band/                          Shared library (import as `band`)
  agents/base.py               bootstrap_env, load_creds, adapter_sdk, create_and_run
  agents/sdk/                  claude_sdk, codex_sdk, gemini_sdk adapters
  client.py                    BandHumanClient, BandAgentClient (thenvoi_rest wrappers)
  config.py                    Settings from .env (ROOT_DIR, adapter type, URLs, keys)
  registry.py                  AGENT_DEFINITIONS (8 agents), load/save agent_config.yaml
  prompts.py                   System prompts for all LLM roles
  approval.py                  Regex helpers for approve/reject (not wired into runtime)
  tools/demo_app.py            HTTP tools against demo-app
  tools/github_ops.py          git/gh operations + publish_agent_pr
  tools/memory_ops.py          Room context + store_incident_memory

agents/<role>/main.py          Entry point per agent; run with `python -m agents.<role>.main`
agents/band_orchestrator/      Meta-agent + generator, converter, company_agent, template/
demo-app/                      Separate FastAPI app (own pyproject.toml, Docker)
generated_agents/              Created at runtime by orchestrator (gitignored)
scripts/                       setup_agents.py, run_all.py, demo.py
tests/                         pytest unit tests
```

Root `main.py` is a placeholder — **not used** in agent flows.

## Agent bootstrap pattern

Every LLM agent follows the same shape:

```python
from band.agents.base import adapter_sdk, create_and_run
from band.prompts import SOME_PROMPT

def build_adapter():
    return adapter_sdk(SOME_PROMPT, additional_tools=[...], enable_memory=False)

def cli() -> None:
    create_and_run(build_adapter(), "config_key", "Human Label")
```

- Credentials loaded from `agent_config.yaml` by config key (e.g. `fix_engineer`).
- `create_and_run` builds `thenvoi.Agent` and runs the WebSocket loop.
- Custom tools use `(PydanticInputModel, handler)` tuples via `CustomToolDef`.

**Exceptions:**

| Agent | Difference |
| ----- | ---------- |
| `watchdog` | No LLM; `monitor_loop()` in `agent_core/helper.py` |
| `log_analyst` | `LangGraphAdapter` + Featherless when `FEATHERLESS_API_KEY` set |
| `compliance_officer` | `LangGraphAdapter` + AI/ML API when `AIML_API_KEY` set |
| `band_orchestrator` | `adapter_sdk` + 8 orchestrator tools in `main.py` |

## Registered agents (`band/registry.py`)

| Config key | Band name | Module |
| ---------- | --------- | ------ |
| `watchdog` | watchdog | `agents.watchdog.main` |
| `incident_commander` | incident-commander | `agents.commander.main` |
| `log_analyst` | log-analyst | `agents.log_analyst.main` |
| `fix_engineer` | fix-engineer | `agents.fix_engineer.main` |
| `reviewer` | reviewer | `agents.reviewer.main` |
| `compliance_officer` | compliance-officer | `agents.compliance.main` |
| `scribe` | scribe | `agents.scribe.main` |
| `band_orchestrator` | band-orchestrator | `agents.band_orchestrator.main` |

Register all via `uv run python scripts/setup_agents.py` (requires `BAND_HUMAN_API_KEY`).

## Adapter selection

`DEFAULT_ADAPTER_TYPE` env (default `claude`) → `band.agents.base.adapter_sdk()`:

- `claude` → `ClaudeSDKAdapter` (local Claude Code CLI)
- `codex` → `CodexAdapter`
- `gemini` → `GoogleADKAdapter`

Log Analyst and Compliance Officer bypass this when their provider API keys are configured.

Band Orchestrator's `generator.py` and `converter.py` call `google.genai` directly (`gemini-2.5-flash`), independent of `DEFAULT_ADAPTER_TYPE`.

## Custom tools by agent

### Fix Engineer (`band.tools.github_ops` + `demo_app`)

`getrepoinfo`, `clonerepo`, `createbranch`, `writefile`, `commitpush`, `openpr`, `mergepr`, `restoreservice`, `fetchhealth`

`mergepr` triggers `demo_app.clear_chaos()` after merge.

### Log Analyst (`band.tools.demo_app`)

`fetchlogs`, `fetchmetrics`, `fetchchaosstatus`, `fetchhealth`

### Reviewer

`fetchprdiff`

### Scribe (`band.tools.memory_ops`)

`fetchroomcontext`, `storeincidentmemory`

### Band Orchestrator (`agents/band_orchestrator/agent_core/schema.py`)

`createbandagent`, `convertagent`, `listgeneratedagents`, `stopgeneratedagent`, `publishagent`, `createcompanycontextagent`, `buildcompanycontext`, `deploycompanycontextagent`

Tool names derive from Pydantic class names: strip `Input`, lowercase (e.g. `CreateBandAgentInput` → `createbandagent`).

## Band Orchestrator internals

### Generated agent layout (`generator.py`)

```
generated_agents/<slug>_<uuid8>/
  main.py
  base.py                 # loads local agent_config.yaml, runs adapter_sdk
  agent_config.yaml       # nested: agent: { name, agent_id, api_key }
  agent_core/
    prompt.py             # AGENT_PROMPT
    tools.py              # Gemini-generated get_tools() or empty fallback
```

### Converter (`converter.py`)

Reads `.py` files from user folder, retrieves Band SDK context via token-overlap retriever (`retriever.py` + `docs/band_sdk.md`), Gemini writes `band_integration.py`, sandbox-validated.

### Company context template (`template/company_agent/`)

- Build scripts: `scripts/build_code_graph.py`, `scripts/build_docs_rag.py`
- Tools: `querycontext`, `getgraphoverview`, `getfiledependencies`
- Requires `sentence-transformers` (run via `uv run` when available)

### Process manager (`process_runner.py`)

Singleton `process_manager` spawns `subprocess.Popen` per agent. `stop()` terminates PIDs but **does not delete** `generated_agents/` folders. `atexit` + signal handlers clean up children.

## agent_config.yaml

War-room agents use flat top-level keys:

```yaml
fix_engineer:
  agent_id: "<uuid>"
  api_key: "<band-api-key>"
  handle: fix-engineer   # optional
```

Generated agents use nested shape:

```yaml
agent:
  name: my_agent_abc12345
  agent_id: "<uuid>"
  api_key: "<key>"
```

## Scripts

| Script | Purpose |
| ------ | ------- |
| `setup_agents.py` | Register missing agents on Band; merge into `agent_config.yaml`. `--dry-run` |
| `run_all.py` | Spawn agent subprocesses. Flags: `--skip-watchdog`, `--skip-compliance`, `--skip-reviewer`, `--run-band-orchestrator`, `--run-only-band-orc` |
| `demo.py` | Inject chaos: `outage` / `pii` / `deploy` / `all`. `--clear`, `--wait SECONDS` |

## Demo app chaos modes

| Scenario | Fault enum | Effect |
| -------- | ---------- | ------ |
| `outage` | `pool_exhaustion` | `/health` unhealthy; checkout 503 |
| `pii` | `pii_leak` | Error logs contain PII; health unhealthy |
| `deploy` | `bad_config` | 85% error rate on checkout/health |

Chaos state lives in `demo-app/app/chaos.py`. Pool exhaustion is flag-only (no real DB pool exhaustion).

## Prompts and coordination

All prompts in `band/prompts.py`. Key behaviors:

- Commander recruits via `thenvoi_lookup_peers` + `thenvoi_add_participant`
- Human SRE approves in chat only (`approve`, `LGTM`, `ship it`) — not programmatic
- `_CODE_CONTEXT_HELPER` appended to commander, fix-engineer, reviewer, compliance prompts for optional company-context agent @mentions
- Commander must not ask humans to run `curl` or `gh` — that's Fix Engineer's job

## Adding a new war-room agent

1. Add entry to `AGENT_DEFINITIONS` in `band/registry.py`
2. Add example credentials to `agent_config.yaml.example`
3. Create `agents/<name>/main.py` following `create_and_run` pattern
4. Add prompt to `band/prompts.py`
5. Optional: add `[project.scripts]` entry in `pyproject.toml`
6. Add to `scripts/run_all.py` `AGENTS` list if it should start by default
7. Register via `setup_agents.py`

## Adding orchestrator capabilities

1. Define Pydantic input in `agents/band_orchestrator/agent_core/schema.py`
2. Implement handler in `main.py` or a module under `agent_core/`
3. Register `(InputModel, handler)` in `_custom_tools()`
4. Document workflow in `ORCHESTRATOR_PROMPT` (`band/prompts.py`)

## Testing

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

Tests do **not** cover live Band WebSocket loops, Gemini generation, or real `gh` operations. Company-context tests build indexes from local fixtures.

Known issue: `tests/test_watchdog.py` may import `_find_peer_id` from `main` but the function lives in `agent_core/helper.py`.

## Environment and secrets

- Never commit `agent_config.yaml` with real API keys (use `.example` as template)
- `GITHUB_TOKEN` needed for Fix Engineer PR flow
- `AGENTS_REPO` for orchestrator `publishagent` (falls back to `DEMO_APP_REPO`)
- Provider keys are optional fallbacks; default path uses Claude Code CLI

## Common tasks

```bash
# Install
uv sync

# Register agents
uv run python scripts/setup_agents.py

# Start incident agents
uv run python scripts/run_all.py

# Start with orchestrator
uv run python scripts/run_all.py --run-band-orchestrator

# Trigger outage
uv run python scripts/demo.py outage

# Run single agent
uv run python -m agents.commander.main
```

## What not to assume

- README agent counts and framework names were historically wrong — trust this file and source.
- Reviewer is **not** hardcoded to Codex; it uses `adapter_sdk()`.
- Compliance uses LangGraph, not PydanticAI, despite band-sdk including pydantic-ai extras.
- `band/approval.py` helpers exist but approval is prompt-driven only.
- `recall_similar_incidents` in `memory_ops.py` is unused; commander uses platform `thenvoi_list_memories`.
- Orchestrator `StopGeneratedAgentInput` docstring mentions file cleanup; `process_manager.stop()` only kills the process.
