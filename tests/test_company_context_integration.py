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


def test_coder_prompt_enforces_real_files_and_present_participants():
    from band.prompts import CODER_PROMPT

    # Coder must read real files before editing (no hallucinated paths/content).
    assert "read_file" in CODER_PROMPT
    assert "list_repo_files" in CODER_PROMPT
    assert "never guess" in CODER_PROMPT.lower()
    # Roster guidance: only coordinate with teammates actually present (never invent one).
    assert "only coordinate with participants who are actually present" in CODER_PROMPT.lower()


def test_prompts_define_single_linear_pipeline_and_loop_rules():
    from band.prompts import COMMANDER_PROMPT, PLANNER_PROMPT, REVIEWER_PROMPT

    for prompt in (COMMANDER_PROMPT, PLANNER_PROMPT, REVIEWER_PROMPT):
        assert "THE PIPELINE" in prompt
        assert "exactly once" in prompt.lower() or "at most one" in prompt.lower()
    # Reviewer must address the human about critical changes.
    assert "human" in REVIEWER_PROMPT.lower()
