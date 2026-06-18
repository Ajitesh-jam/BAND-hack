"""Integration-style tests for company context agent query tools."""

from __future__ import annotations

import sys
from pathlib import Path

from agents.band_orchestrator.agent_core import company_agent


def test_query_tools_return_graph_and_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(company_agent, "GENERATED_DIR", tmp_path)
    scaffold = company_agent.scaffold_company_agent(
        agent_id="ctx-id",
        api_key="ctx-key",
        name="company_context",
    )
    folder = Path(scaffold["folder"])
    (folder / "docs" / "incidents.md").write_text(
        "Commander recruits planner. Coder uses github_ops.",
        encoding="utf-8",
    )
    build = company_agent.build_company_context(name=scaffold["name"])
    assert build["ok"] is True

    sys.path.insert(0, str(folder))
    try:
        from agent_core.code_graph import get_graph_overview, query_graph
        from agent_core.docs_rag import retrieve_docs

        overview = get_graph_overview(agent_root=folder)
        assert overview["ok"] is True

        graph = query_graph("github_ops", agent_root=folder)
        docs = retrieve_docs("commander planner coder", agent_root=folder)
        assert docs["ok"] is True
        assert docs["chunks"]
    finally:
        sys.path.remove(str(folder))


def test_coder_prompt_has_local_repo_tools_no_push():
    from band.prompts import CODER_PROMPT

    assert "read_file" in CODER_PROMPT
    assert "write_file" in CODER_PROMPT
    assert "github_agent" in CODER_PROMPT.lower()
    assert "do not push" in CODER_PROMPT.lower() or "not push" in CODER_PROMPT.lower()


def test_planner_prompt_has_readonly_repo_tools():
    from band.prompts import PLANNER_PROMPT

    assert "read_file" in PLANNER_PROMPT
    assert "do not push" in PLANNER_PROMPT.lower() or "not push" in PLANNER_PROMPT.lower()


def test_github_agent_prompt_push_only():
    from band.prompts import GITHUB_AGENT_PROMPT

    assert "commit_and_push" in GITHUB_AGENT_PROMPT or "commit" in GITHUB_AGENT_PROMPT.lower()
    assert "open_pull_request" in GITHUB_AGENT_PROMPT or "open pr" in GITHUB_AGENT_PROMPT.lower()
    assert "merge_pull_request" in GITHUB_AGENT_PROMPT.lower()
    assert "commander" in GITHUB_AGENT_PROMPT.lower()


def test_reviewer_approve_handoff_includes_github_next():
    from band.prompts import REVIEWER_PROMPT

    assert "NEXT_FOR_COMMANDER" in REVIEWER_PROMPT
    assert "github_agent" in REVIEWER_PROMPT.lower()
    assert "merge_pull_request" in REVIEWER_PROMPT.lower()


def test_prompts_define_single_linear_pipeline_and_loop_rules():
    from band.prompts import COMMANDER_PROMPT, DOCUMENTATION_PROMPT, PLANNER_PROMPT, REVIEWER_PROMPT

    for prompt in (COMMANDER_PROMPT, PLANNER_PROMPT, REVIEWER_PROMPT):
        assert "THE CHAIN" in prompt
        assert "ALLOWED MENTIONS" in prompt
    assert "request_approval" in COMMANDER_PROMPT
    assert "documentation_agent" in PLANNER_PROMPT
    assert "fetch_health" in REVIEWER_PROMPT.lower() or "fetchhealth" in REVIEWER_PROMPT.lower()
    assert "fetchprdiff" in REVIEWER_PROMPT.lower() or "local" in REVIEWER_PROMPT.lower()
    assert "querycontext" in DOCUMENTATION_PROMPT.lower()
    assert "human" in DOCUMENTATION_PROMPT.lower()
    assert "stay silent" not in DOCUMENTATION_PROMPT.lower() or "only when" in DOCUMENTATION_PROMPT.lower()
