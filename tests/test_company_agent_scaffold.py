"""Tests for company context agent scaffolding."""

from __future__ import annotations

from pathlib import Path

from agents.band_orchestrator.agent_core import company_agent


def test_scaffold_company_agent_creates_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(company_agent, "GENERATED_DIR", tmp_path)
    result = company_agent.scaffold_company_agent(
        agent_id="test-agent-id",
        api_key="test-api-key",
        name="company_context",
    )
    assert result["ok"] is True
    folder = Path(result["folder"])
    assert folder.exists()
    assert (folder / "main.py").exists()
    assert (folder / "agent_core" / "tools.py").exists()
    assert (folder / "docs").is_dir()
    assert (folder / "embedding_config.yaml").exists()
    assert (folder / "scripts" / "build_docs_rag.py").exists()
    assert (folder / "scripts" / "build_code_graph.py").exists()


def test_build_company_context_local_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(company_agent, "GENERATED_DIR", tmp_path)
    scaffold = company_agent.scaffold_company_agent(
        agent_id="test-agent-id",
        api_key="test-api-key",
        name="company_context",
    )
    folder = Path(scaffold["folder"])
    (folder / "docs" / "guide.md").write_text(
        "See band/tools/github_ops.py for GitHub operations.",
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parent.parent
    build = company_agent.build_company_context(
        name=scaffold["name"],
        github_url=None,
    )
    assert build["ok"] is True
    assert (folder / "data" / "docs_index.json").exists()
    assert (folder / "data" / "code_graph.json").exists()

