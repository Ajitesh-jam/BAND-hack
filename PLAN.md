# BAND-hack Rebuild Plan — Orchestrator-Led Autonomous Dev Team

> **For the executor (composer-2.5):** This is a complete, self-contained spec. You have no prior chat context — everything you need is here. Work phase by phase. After each phase, run its acceptance check before moving on. Do **not** implement Cursor SDK or Cursor cloud. Use the existing Claude Code SDK and Codex SDK adapters. Target only the local `demo-app`. Branch is already `feat/orchestrator-dev-team`.

---

## 0. Goal

Rebuild the project around a single pitch: **Band Orchestrator is the highest-authority agent that intelligently spawns and manages a right-sized engineering team on demand.**

The team solves two tasks against `demo-app`:
1. **Fix an error** (triggered by WatchDog detecting an unhealthy app).
2. **Push a feature** (triggered by a human/remote message to the Orchestrator).

Pipeline: **Company Agent (context) → Planner (Opus, optional alpha/beta sub-planners) → Coder (Claude) → Reviewer (Codex) → PR (gh) → human approval → Merger**.

The "intelligence" = the Orchestrator decides *which* agents to spawn and *when*:
- spawns Company Agent + WatchDog at startup,
- spawns alpha/beta planners **only if the codebase is large**,
- spawns the Merger **only after** the Reviewer approves and a human types `approve`.

---

## 1. Locked decisions

| Decision | Choice |
|---|---|
| Code editing | **Local edits** in a working clone of `demo-app`; **`gh` CLI** for PRs/merge |
| Cursor SDK / cloud | **Do not use.** Coder/Planner = Claude Code SDK; Reviewer = Codex SDK |
| Target repo | `demo-app` only |
| Scope | Remove every agent/module not used by the new flow |
| Approval | PR merge is gated on a human `approve` message in the Band room |

Model assignment (configurable via env, see §8):
- Orchestrator → Claude `sonnet`
- Planner / alpha / beta → Claude `opus`
- Coder → Claude `sonnet`
- Reviewer → Codex (existing `codex_code_model`)
- Company Agent → deterministic build (AST graph + sentence-transformers RAG); Claude `sonnet` for Q&A
- WatchDog / Merger → no LLM

---

## 2. Target architecture

### Persistent agents (registered, started at install)
| Key | Module | Brain | Purpose |
|---|---|---|---|
| `band_orchestrator` | `agents/band_orchestrator/main.py` | Claude sonnet | Spine; spawns/recruits all others; routes triggers; gates merge |
| `company_agent` | `agents/company_agent/main.py` | deterministic + Claude | Builds & serves code graph + docs RAG over `demo-app` |
| `watchdog` | `agents/watchdog/main.py` | none | Polls `demo-app /health`; on failure notifies Orchestrator |

### Per-task agents (spawned on demand by Orchestrator)
| Key | Module | Brain | Purpose |
|---|---|---|---|
| `planner` | `agents/planner/main.py` | Claude opus | Produces structured plan; requests alpha/beta if repo big |
| `planner_alpha` | `agents/planner/main.py` (alpha cfg) | Claude opus | Plans a partition of the codebase |
| `planner_beta` | `agents/planner/main.py` (beta cfg) | Claude opus | Plans another partition |
| `coder` | `agents/coder/main.py` | Claude sonnet | Implements plan via git tools (local edits) |
| `reviewer` | `agents/reviewer/main.py` | Codex | Reviews branch diff; routes feedback; opens PR when good |
| `merger` | `agents/merger/main.py` | none | Merges PR after human approval; clears chaos |

> Coordination model: **Band-native, single room.** Agents are real Band participants and coordinate via `@mention`s in one incident/task room. The Orchestrator spawns each via `process_manager.spawn(...)` and adds it with `thenvoi_add_participant`. This is the demo's wow factor — keep it.

---

## 3. End-to-end flows

### Flow A — Fix error
1. `scripts/demo.py outage` injects chaos → `demo-app /health` becomes unhealthy.
2. WatchDog detects failure (after threshold) → creates a Band room, adds the **Orchestrator**, posts an alert `@band-orchestrator`.
3. Orchestrator ensures Company Agent is in the room; spawns + adds **Planner**, hands it the alert + tells it to consult Company Agent.
4. Planner queries Company Agent (graph + docs). If repo is "big" (see §7.4), Planner asks Orchestrator to spawn **alpha/beta**; each plans a partition; Planner merges into one plan.
5. Planner posts the final plan, `@`-mentions Orchestrator.
6. Orchestrator spawns **Coder**, hands it the plan. Coder clones/uses `demo-app`, creates a branch, edits files, commits.
7. Coder posts branch name + summary, `@`-mentions Orchestrator.
8. Orchestrator spawns **Reviewer**. Reviewer reads the branch diff. If problems → `@`-mention Coder (impl bug) or Planner (plan flaw); bounded to `REVIEW_MAX_ROUNDS`. If good → Reviewer opens a PR (`gh`) and posts the PR URL.
9. Orchestrator asks the human SRE to `approve` in chat. On `approve`, it spawns **Merger**.
10. Merger merges the PR (`gh ... --squash`) and clears chaos. WatchDog sees `/health` recover and posts resolution.

### Flow B — Push feature
Same as A, but the trigger is a human/remote message to the Orchestrator describing the feature (no WatchDog, no chaos clear). Merger just merges the PR.

---

## 4. Current codebase inventory (what exists today)

Reusable as-is or with edits:
- `band/agents/base.py` — `adapter_sdk(prompt, adapter_type=None, model=None, *, additional_tools, enable_memory, permission_mode)`, `create_and_run(adapter, agent_name, label)`.
- `band/agents/sdk/claude_sdk.py` — `claude_agent(prompt, model, *, additional_tools, enable_memory, permission_mode)`.
- `band/agents/sdk/codex_sdk.py` — `codex_agent(prompt, model, *, additional_tools, enable_memory, permission_mode)`.
- `band/agents/sdk/gemini_sdk.py` — keep (unused by default).
- `band/client.py` — `BandAgentClient` (create_chat, list_peers, add_participant, send_message, send_event, etc.).
- `band/config.py` — pydantic `Settings`; `get_settings()`.
- `band/registry.py` — `AGENT_DEFINITIONS`, `load_agent_config`, `save_agent_config`.
- `band/prompts.py` — prompts (to be rewritten).
- `band/approval.py` — `is_approval_message`, `is_rejection_message` (WIRE these into the merge gate).
- `band/tools/github_ops.py` — `clone_or_pull_repo()`, `create_branch(name)`, `write_file(rel, content)`, `commit_and_push(msg, branch)`, `open_pull_request(title, body, branch, base=None)`, `fetch_pr_diff(pr)`, `merge_pull_request(pr)` (merges + clears chaos), `get_repo_info()`, `default_branch()`. **Local-mode fallback** when `DEMO_APP_REPO` is empty (edits in-repo `demo-app/`, simulated PR URL).
- `band/tools/demo_app.py` — `fetch_health`, `fetch_logs`, `fetch_metrics`, `fetch_chaos_status`, `clear_chaos`, etc.
- `agents/band_orchestrator/agent_core/process_runner.py` — `process_manager` singleton: `.spawn(name, script_path, cwd, log_path)`, `.stop(name)`, `.list_agents()`, `.folder_for(name)`. **Reuse.**
- `agents/band_orchestrator/agent_core/company_agent.py` + `template/company_agent/` — scaffold + build code graph + docs RAG. **Reuse as the new persistent Company Agent's engine.**
- `agents/watchdog/agent_core/helper.py` — `monitor_loop`, `check_health`, `classify_failure`, `open_incident_room` (currently recruits *commander* — change to *orchestrator*).
- `agents/fix_engineer/` — its `agent_core/schema.py` (git tool input models) and tool wiring are the basis for the new **Coder**.
- `scripts/demo.py`, `scripts/setup_agents.py` — keep.
- `demo-app/` — keep (the target).

---

## 5. DELETE (remove everything not needed)

Delete these paths:
- `agents/commander/`
- `agents/log_analyst/`
- `agents/compliance/`
- `agents/scribe/`
- `agents/process_runner/` (stray duplicate, if present)
- `agents/band_integrator/` (if any remnants remain)
- `agents/band_orchestrator/agent_core/generator.py` (runtime Gemini codegen — not used by new flow)
- `agents/band_orchestrator/agent_core/converter.py`
- `agents/band_orchestrator/agent_core/retriever.py`
- `agents/band_orchestrator/agent_core/docs/band_sdk.md` (large SDK doc for converter)
- `examples/demo_langgraph_agent/` (convert-agent demo)
- `agents/fix_engineer/` (after porting tool wiring into `agents/coder/`)
- Tests for deleted agents: `tests/test_*` referencing commander/log_analyst/compliance/scribe/converter/generator.

Keep but stop referencing: `band/tools/memory_ops.py` (optional; only if you add postmortem memory later), `band/tools/github_ops.py::publish_agent_pr` (harmless; remove if you want zero dead code).

After deletions, **grep the repo** for `commander`, `log_analyst`, `compliance`, `scribe`, `fix_engineer`, `generator`, `converter`, `band_integrator`, `convertagent`, `createbandagent`, `publishagent` and remove/replace every remaining import or reference.

---

## 6. KEEP

`band/` (all except prompt rewrites), `process_runner.py`, `company_agent.py` + `template/company_agent/`, `watchdog` (with the orchestrator-recruit change), `github_ops.py`, `demo_app.py`, `approval.py`, `scripts/demo.py`, `scripts/setup_agents.py`, `demo-app/`.

---

## 7. CREATE / MODIFY (phased)

> Every LLM agent follows the standard shape:
> ```python
> from band.agents.base import adapter_sdk, create_and_run
> from band.prompts import SOME_PROMPT
> def build_adapter():
>     return adapter_sdk(SOME_PROMPT, adapter_type=..., model=..., additional_tools=[...])
> def cli() -> None:
>     create_and_run(build_adapter(), "<config_key>", "<Label>")
> if __name__ == "__main__":
>     cli()
> ```
> Custom tools are `(PydanticInputModel, handler)` tuples; tool name = class name minus `Input`, lowercased.

### Phase 1 — Prune & config foundation

**1.1** Do all deletions in §5.

**1.2** `band/config.py` — add settings (with env aliases):
```python
orchestrator_model: str = "sonnet"
planner_model: str = "opus"
coder_model: str = "sonnet"
reviewer_adapter: str = "codex"          # reviewer uses codex adapter
coder_adapter: str = "claude"
planner_adapter: str = "claude"
orchestrator_adapter: str = "claude"
big_repo_file_threshold: int = 150        # planner uses this to decide alpha/beta
review_max_rounds: int = 3
orchestrator_handle: str = "band-orchestrator"
company_agent_handle: str = "company-agent"
planner_handle: str = "planner"
coder_handle: str = "coder"
reviewer_handle: str = "reviewer"
merger_handle: str = "merger"
```
Keep existing `watchdog_*`, `demo_app_*`, `claude_code_model`, `codex_code_model`, paths.

**1.3** `band/registry.py` — replace `AGENT_DEFINITIONS` with the final set:
`band_orchestrator`, `company_agent`, `watchdog`, `planner`, `planner_alpha`, `planner_beta`, `coder`, `reviewer`, `merger` (name + description each).

**1.4** `agent_config.yaml.example` and `.env.example` — regenerate for the new agent keys and the new env vars; add `CURSOR_API_KEY` is **not** needed. Keep `GITHUB_TOKEN`, `DEMO_APP_REPO`.

**Acceptance:** `uv run python -c "import band.registry, band.config"` succeeds; `uv run python scripts/setup_agents.py --dry-run` lists the 9 keys; repo grep for deleted names is clean.

---

### Phase 2 — Company Agent (persistent)

Create `agents/company_agent/` as a first-class persistent Band agent wrapping the existing engine in `agents/band_orchestrator/agent_core/company_agent.py` + `template/company_agent/`.

**2.1** `agents/company_agent/agent_core/schema.py` — tool inputs:
- `BuildContextInput { target_path: str | None }` → build/refresh graph+docs over `demo-app` (default path = repo `demo-app/`).
- `QueryContextInput { question: str }` → docs RAG answer.
- `GraphOverviewInput {}` → returns `{files, nodes, edges, communities}` (used by Planner for sizing).
- `FileDependenciesInput { relative_path: str }` → dependents/dependencies for a file.

**2.2** `agents/company_agent/main.py` — `adapter_sdk(COMPANY_AGENT_PROMPT, model=sonnet, additional_tools=[...])`, `create_and_run(..., "company_agent", "Company Agent")`. Handlers call into the existing graph/docs builders (`template/company_agent/agent_core/code_graph.py`, `docs_rag.py`). Point them at the repo's `demo-app/` for the demo.

**2.3** `band/prompts.py::COMPANY_AGENT_PROMPT` — "You hold the company's code knowledge. On `@mention`, answer with graph overview, file dependencies, or doc-grounded answers. Be concise and cite files."

**Acceptance:** start company_agent alone; from a Band room `@company-agent give a graph overview` returns counts; `query` returns a doc-grounded answer.

---

### Phase 3 — WatchDog notifies Orchestrator

**3.1** `agents/watchdog/agent_core/helper.py::open_incident_room` — replace commander recruitment with the **Orchestrator**:
- use `settings.orchestrator_handle` instead of `commander_handle`,
- `_find_peer(peers, settings.orchestrator_handle)`,
- `@mention` the orchestrator in the alert message ("please assemble the team and resolve").

**3.2** Keep `monitor_loop`, `check_health`, `classify_failure`, recovery event logic unchanged.

**Acceptance:** with orchestrator registered, `demo.py outage` → watchdog opens a room and `@band-orchestrator` is added + mentioned.

---

### Phase 4 — Coder (Claude, local edits)

Port `agents/fix_engineer/` → `agents/coder/`.

**4.1** `agents/coder/agent_core/schema.py` — reuse fix_engineer's models: `CloneRepoInput`, `CreateBranchInput{branch_name}`, `WriteFileInput{relative_path, content}`, `CommitPushInput{message, branch}`, `RepoInfoInput`, plus `ReadFileInput{relative_path}` (new; read current file before editing).

**4.2** `agents/coder/main.py` — tools (all from `band.tools.github_ops`, local edits):
`get_repo_info`, `clone_or_pull_repo`, `read_file` (add helper to github_ops, see 4.3), `create_branch`, `write_file`, `commit_and_push`. Adapter: `adapter_sdk(CODER_PROMPT, adapter_type=settings.coder_adapter, model=settings.coder_model, permission_mode="bypassPermissions")`. `create_and_run(..., "coder", "Coder")`.

**4.3** `band/tools/github_ops.py` — add:
- `read_file(relative_path) -> {ok, content}` (read from working clone / local `demo-app`).
- `get_branch_diff(branch, base=None) -> {ok, diff}` → `git diff base...branch` in the working clone (for pre-PR review in Phase 5).

**4.4** `band/prompts.py::CODER_PROMPT` — "You implement the Planner's plan against `demo-app`. Steps: get_repo_info → clone_or_pull_repo → create_branch (e.g. `fix/<slug>` or `feat/<slug>`) → read_file then write_file for each change → commit_and_push. Post the branch name and a short summary, then `@reviewer`. Do not open PRs. Make minimal, correct changes."

**Acceptance:** give the Coder a tiny plan in a room; it creates a branch and commits a change to the working `demo-app` clone; posts branch name.

---

### Phase 5 — Reviewer (Codex) + PR creation

**5.1** `agents/reviewer/agent_core/schema.py` — `BranchDiffInput{branch, base?}`, `OpenPRInput{title, body, branch, base?}`.

**5.2** `agents/reviewer/main.py` — tools: `get_branch_diff`, `open_pull_request` (from github_ops). Adapter: `adapter_sdk(REVIEWER_PROMPT, adapter_type="codex", model=settings.codex_code_model)`. `create_and_run(..., "reviewer", "Reviewer")`.

**5.3** `band/prompts.py::REVIEWER_PROMPT` — "You review the Coder's branch diff (`get_branch_diff`). If you find an implementation bug, `@coder` with specifics. If the *plan* is flawed, `@planner`. Otherwise, open a PR with `open_pull_request` and post the PR URL, then tell `@band-orchestrator` it's ready for human approval. Be specific and adversarial but fair."

**Acceptance:** Reviewer reads a branch diff, and on a clean change opens a PR (real PR if `DEMO_APP_REPO`+`GITHUB_TOKEN` set; simulated URL in local mode) and posts the URL.

---

### Phase 6 — Planner (Opus) + conditional alpha/beta

**6.1** `agents/planner/agent_core/schema.py` — `EmitPlanInput{plan: str, files: list[str]}` (structured plan), `RequestSubPlannersInput{partitions: list[str]}` (ask Orchestrator to spawn alpha/beta).

**6.2** `agents/planner/main.py` — one module, configurable role via env/arg so it can run as `planner`, `planner_alpha`, or `planner_beta` (the config key is passed to `create_and_run`; default `planner`). Tools: `emit_plan`, `request_sub_planners`. Adapter: Claude `opus`. It consults Company Agent by `@mention` (no direct tool needed — coordination via room messages).

**6.3** Sizing logic (in prompt): "Ask `@company-agent` for a graph overview. If `files > BIG_REPO_FILE_THRESHOLD`, call `request_sub_planners` with 2 partitions (by graph communities/top-level packages) and wait for alpha/beta sub-plans, then merge. Otherwise produce a single plan. Emit the final plan with `emit_plan`, then `@band-orchestrator`."

**6.4** `band/prompts.py` — `PLANNER_PROMPT` (and reuse for alpha/beta with a partition note injected by the Orchestrator when spawning).

**Acceptance:** Planner produces a single structured plan for the small demo-app; if you lower `BIG_REPO_FILE_THRESHOLD` below demo-app's file count, it triggers `request_sub_planners`.

---

### Phase 7 — Merger + human approval gate

**7.1** `agents/merger/main.py` — minimal Band agent (no LLM needed; or thin Claude). Tool: `merge_pull_request` (from github_ops — squashes, deletes branch, clears chaos). `create_and_run(..., "merger", "Merger")`.

**7.2** Approval gate lives in the **Orchestrator** (Phase 8): it only spawns/recruits the Merger after `band.approval.is_approval_message(text)` returns True on a human message.

**Acceptance:** after a human types `approve`, the Merger merges the PR and chaos clears; `demo-app /health` returns healthy.

---

### Phase 8 — Orchestrator (spine) rewrite

**8.1** `agents/band_orchestrator/agent_core/schema.py` — replace all old tool inputs with:
- `DeployAgentInput{role: str, partition?: str}` — generic spawn for `company_agent|watchdog|planner|planner_alpha|planner_beta|coder|reviewer|merger`. Handler: resolve module path + config key from a role→(module, config_key) map, `process_manager.spawn(...)`, then return the `agent_id` so the orchestrator can `thenvoi_add_participant`.
- `ListAgentsInput{}` → `process_manager.list_agents()`.
- `StopAgentInput{name}` → `process_manager.stop(name)`.

**8.2** `agents/band_orchestrator/main.py` — rewrite:
- imports: `process_manager`, `adapter_sdk`, `create_and_run`, `ORCHESTRATOR_PROMPT`, the schema above, `band.registry.load_agent_config`, `band.config`.
- `_deploy_agent(inp)`: map role → (`script_path`, `cwd`, `config_key`); spawn; read that agent's `agent_id` from `load_agent_config(config_key)`; return `{status, name, pid, agent_id, next_step: "call thenvoi_add_participant with agent_id=..."}`.
- `build_adapter()`: `adapter_sdk(ORCHESTRATOR_PROMPT, adapter_type=settings.orchestrator_adapter, model=settings.orchestrator_model, additional_tools=[deploy/list/stop], enable_memory=True)`.
- `cli()`: `create_and_run(build_adapter(), "band_orchestrator", "Band Orchestrator")`.

**8.3** `band/prompts.py::ORCHESTRATOR_PROMPT` — encode the policy:
```
You are the Band Orchestrator, highest authority. You build and manage the team.
On startup (no incident yet): ensure company_agent and watchdog are deployed (deploy_agent) and in the room.
When an incident/feature task arrives:
1. Ensure company_agent is present.
2. deploy_agent("planner"); add it; @planner with the task + tell it to consult @company-agent.
3. If planner calls request_sub_planners: deploy_agent("planner_alpha", partition=...) and ("planner_beta", partition=...); add them; @them with their partitions.
4. When planner emits a final plan: deploy_agent("coder"); add it; @coder with the plan.
5. When coder posts a branch: deploy_agent("reviewer"); add it; @reviewer with the branch.
6. Reviewer loops with @coder/@planner up to REVIEW_MAX_ROUNDS. When reviewer posts a PR URL: ask the human SRE to type `approve`.
7. ONLY after a human approval message: deploy_agent("merger"); add it; @merger with the PR URL.
8. After merge + health recovery, summarize and stop per-task agents (stop_agent) to free resources.
Never ask humans to run gh/curl/git — agents do that. Keep messages concise and operational.
```
Wire `band.approval.is_approval_message` into the orchestrator's decision (it should not deploy the merger until it sees an approval from a human participant).

**Acceptance:** full Flow A works end to end (see §9).

---

### Phase 9 — Scripts, run, docs

**9.1** `scripts/run_all.py` — rewrite. Default: start **orchestrator + company_agent + watchdog** (persistent). Flags: `--run-only-orchestrator`. The orchestrator spawns planner/coder/reviewer/merger on demand. Update `REQUIRED_AGENTS` accordingly.

**9.2** `scripts/demo.py` — unchanged (chaos injection). Optionally add a `feature "<description>"` subcommand that posts a feature request to a fresh room `@band-orchestrator` (nice-to-have).

**9.3** Update `README.md` and `AGENTS.md` to the new architecture; remove references to deleted agents. (Keep edits factual; do not re-introduce old agent tables.)

**9.4** Update/replace `tests/`: keep `test_github_ops.py` (extend with `read_file`, `get_branch_diff`), `test_company_context_*` (now point at `agents/company_agent`), add a `test_registry.py` for the new keys. Remove tests for deleted agents.

**Acceptance:** `uv run pytest` passes; `uv run ruff check .` clean.

---

## 8. Configuration summary

`.env` additions:
```
# Per-role models / adapters
ORCHESTRATOR_MODEL=sonnet
PLANNER_MODEL=opus
CODER_MODEL=sonnet
# Reviewer uses codex adapter (CODEX_CODE_MODEL)
BIG_REPO_FILE_THRESHOLD=150
REVIEW_MAX_ROUNDS=3
# For real PRs (else local-mode simulated PRs):
DEMO_APP_REPO=https://github.com/<owner>/<demo-app-repo>
GITHUB_TOKEN=<token with repo scope>
```

`agent_config.yaml` must contain credentials for all 9 keys. Register with:
```
uv run python scripts/setup_agents.py        # needs BAND_HUMAN_API_KEY
```

> **PR note:** With `DEMO_APP_REPO` empty, `github_ops` runs in **local mode**: Coder edits the in-repo `demo-app/` directly and PR/merge are simulated (merge clears chaos). To get real `gh` PRs, set `DEMO_APP_REPO` to the demo-app's own GitHub repo + `GITHUB_TOKEN`. Both paths must work; test local mode first.

---

## 9. Final end-to-end acceptance (Flow A)

```bash
# 1. demo app up
cd demo-app && docker compose up --build -d && curl -s localhost:8080/health && cd ..
# 2. register agents (once)
uv run python scripts/setup_agents.py
# 3. start persistent agents
uv run python scripts/run_all.py
# 4. trigger outage
uv run python scripts/demo.py outage
```
Expected in the Band UI:
1. WatchDog opens a room, adds + `@`-mentions **Band Orchestrator**.
2. Orchestrator pulls in Company Agent, spawns **Planner**; Planner consults Company Agent and emits a plan.
3. Orchestrator spawns **Coder** → branch + commit on `demo-app` clone.
4. Orchestrator spawns **Reviewer** → reviews diff → opens PR (or simulated) → posts URL.
5. Orchestrator asks for approval; type **`approve`** in the room.
6. Orchestrator spawns **Merger** → merges → chaos clears → WatchDog reports healthy.

Flow B: in a room, `@band-orchestrator add a /readiness endpoint to demo-app` → same pipeline, ends with a merged PR (no chaos).

---

## 10. Guardrails

- **Bounded review loop:** stop after `REVIEW_MAX_ROUNDS`; escalate to human with a summary.
- **Merge only after human approval:** enforce via `band.approval.is_approval_message`; never auto-merge.
- **Idempotent spawns:** `process_manager.spawn` returns `already_running` if a role is live — don't double-spawn.
- **Local-mode first:** ensure the whole flow works with `DEMO_APP_REPO` empty before testing real `gh` PRs.
- **No secrets in git:** `agent_config.yaml` is gitignored; keep it that way.
- **After code changes:** run `graphify update .` to refresh the knowledge graph, then `uv run ruff check .` and `uv run pytest`.

---

## 11. Suggested commit sequence (one commit per phase)

1. `chore: prune unused agents; add per-role config + registry`
2. `feat: company agent (persistent code-context)`
3. `feat: watchdog notifies orchestrator`
4. `feat: coder agent (claude, local edits)`
5. `feat: reviewer agent (codex) + PR creation`
6. `feat: planner agent (opus) + conditional alpha/beta`
7. `feat: merger agent + human approval gate`
8. `feat: orchestrator spine rewrite (deploy/recruit policy)`
9. `chore: scripts, run_all, docs, tests`
