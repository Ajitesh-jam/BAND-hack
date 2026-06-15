"""Custom tools for the company code-context agent."""

from __future__ import annotations

import json

from thenvoi.runtime.custom_tools import CustomToolDef

from agent_core.code_graph import get_file_dependencies, get_graph_overview, query_graph
from agent_core.docs_rag import retrieve_docs
from agent_core.schema import GetFileDependenciesInput, GetGraphOverviewInput, QueryContextInput


def _query_context(inp: QueryContextInput) -> str:
    graph = query_graph(inp.query)
    docs = retrieve_docs(inp.query)
    return json.dumps({
        "graph_context": {
            "summary": graph.get("summary", ""),
            "matches": graph.get("matches", []),
            "neighborhood": graph.get("neighborhood", []),
            "node_count": graph.get("node_count", 0),
            "edge_count": graph.get("edge_count", 0),
        },
        "doc_chunks": docs.get("chunks", []),
        "doc_sources": docs.get("sources", []),
        "retrieval_mode": docs.get("mode", "none"),
    })


def _get_graph_overview(_: GetGraphOverviewInput) -> str:
    return json.dumps(get_graph_overview())


def _get_file_dependencies(inp: GetFileDependenciesInput) -> str:
    return json.dumps(get_file_dependencies(inp.file_path))


def get_tools() -> list[CustomToolDef]:
    return [
        (QueryContextInput, _query_context),
        (GetGraphOverviewInput, _get_graph_overview),
        (GetFileDependenciesInput, _get_file_dependencies),
    ]
