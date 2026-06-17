"""Tests for context engine build."""

from __future__ import annotations

from agents.band_orchestrator.agent_core import context_engine


def test_build_context_demo_app(monkeypatch, tmp_path):
    monkeypatch.setattr(context_engine, "COMPANY_AGENT_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("demo-app uses FastAPI", encoding="utf-8")

    result = context_engine.build_context()
    assert "graph" in result
    assert "docs" in result
    assert result["docs"].get("ok") is True
