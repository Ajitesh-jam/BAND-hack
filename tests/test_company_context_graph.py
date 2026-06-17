"""Tests for company context code graph builder."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TEMPLATE_ROOT = (
    Path(__file__).resolve().parent.parent
    / "agents"
    / "band_orchestrator"
    / "template"
    / "company_agent"
)
sys.path.insert(0, str(TEMPLATE_ROOT))

from agent_core.code_graph import (  # noqa: E402
    build_graph_from_repo,
    get_file_dependencies,
    query_graph,
    save_graph,
)


def test_build_graph_from_local_repo():
    repo_root = Path(__file__).resolve().parent.parent
    graph = build_graph_from_repo(repo_root)
    assert len(graph["nodes"]) > 0
    assert isinstance(graph["edges"], list)
    assert graph["architecture_summary"]


def test_query_graph_and_dependencies(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    graph = build_graph_from_repo(repo_root)
    save_graph(graph, agent_root=tmp_path)

    result = query_graph("github_ops", agent_root=tmp_path)
    assert result["ok"] is True

    overview_path = tmp_path / "data" / "code_graph.json"
    assert overview_path.exists()

    if graph["nodes"]:
        sample = graph["nodes"][0]["path"]
        deps = get_file_dependencies(sample, agent_root=tmp_path)
        assert deps["ok"] is True
        assert deps["file"]
