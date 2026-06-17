"""Tests for graphify integration."""

from __future__ import annotations

from band.tools import graphify_ops


def test_graph_overview_demo_app():
    result = graphify_ops.graph_overview()
    if result.get("ok"):
        assert result["files"] >= 1
        assert result["nodes"] >= 1
    else:
        # graph may not be built in CI — build_graph is tested separately
        assert "no graph" in result.get("error", "").lower()


def test_context_paths_include_graphify():
    paths = graphify_ops.context_paths()
    assert "graph_dir" in paths
    assert "graphify-out" in paths["graph_dir"]
    assert paths["docs_dir"].endswith("company_agent/docs")
