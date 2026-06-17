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
        "Incident commander recruits log analyst. Fix engineer uses github_ops.",
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
        docs = retrieve_docs("incident commander fix engineer", agent_root=folder)
        assert docs["ok"] is True
        assert docs["chunks"]
    finally:
        sys.path.remove(str(folder))


def test_fix_engineer_prompt_mentions_code_context_only_when_present():
    from band.prompts import FIX_ENGINEER_PROMPT

    assert "thenvoi_get_participants" in FIX_ENGINEER_PROMPT
    assert "do not mention or recruit one" in FIX_ENGINEER_PROMPT.lower()
