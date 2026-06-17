"""Build and query company context — graphify for code, local RAG for docs."""

from __future__ import annotations

import logging

from band.config import ROOT_DIR
from band.tools import graphify_ops

logger = logging.getLogger(__name__)

COMPANY_AGENT_ROOT = ROOT_DIR / "agents" / "company_agent"


def build_context(target_path: str | None = None) -> dict:
    """Deterministic build: graphify AST graph + docs RAG index (no LLM)."""
    from agents.company_agent.agent_core.docs_rag import build_docs_index

    graph_result = graphify_ops.build_graph(target_path)
    docs_result = build_docs_index(agent_root=COMPANY_AGENT_ROOT)
    ok = bool(graph_result.get("ok") or docs_result.get("ok"))
    paths = graphify_ops.context_paths(target_path)
    return {
        "ok": ok,
        "graph": graph_result,
        "docs": docs_result,
        "paths": paths,
    }


def query_docs(question: str) -> dict:
    from agents.company_agent.agent_core.docs_rag import query_docs as _query

    return _query(question, agent_root=COMPANY_AGENT_ROOT)
