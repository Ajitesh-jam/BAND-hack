"""Custom tools for the company documentation agent."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from thenvoi.runtime.custom_tools import CustomToolDef

from band.config import get_settings

from agent_core.code_graph import (
    get_commit_history,
    get_file_dependencies,
    get_graph_overview,
    query_graph,
)
from agent_core.docs_rag import retrieve_docs
from agent_core.schema import (
    GetCommitHistoryInput,
    GetFileDependenciesInput,
    GetGraphOverviewInput,
    QueryContextInput,
    UpdateGraphInput,
)

AGENT_ROOT = Path(__file__).resolve().parent.parent


def _query_context(inp: QueryContextInput) -> str:
    graph = query_graph(inp.query)
    docs = retrieve_docs(inp.query)
    commits = get_commit_history(inp.query, limit=5)
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
        "commit_context": commits,
    })


def _get_graph_overview(_: GetGraphOverviewInput) -> str:
    return json.dumps(get_graph_overview())


def _get_file_dependencies(inp: GetFileDependenciesInput) -> str:
    return json.dumps(get_file_dependencies(inp.file_path))


def _get_commit_history(inp: GetCommitHistoryInput) -> str:
    return json.dumps(get_commit_history(inp.query, limit=inp.limit))


def _update_graph(inp: UpdateGraphInput) -> str:
    settings = get_settings()
    github_url = inp.github_url or settings.company_repo_url or settings.demo_app_repo
    cmd = [
        sys.executable,
        str(AGENT_ROOT / "scripts" / "build_code_graph.py"),
        "--agent-root",
        str(AGENT_ROOT),
    ]
    if github_url:
        cmd.extend(["--github-url", github_url])
    graph = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    docs_cmd = [
        sys.executable,
        str(AGENT_ROOT / "scripts" / "build_docs_rag.py"),
        "--agent-root",
        str(AGENT_ROOT),
    ]
    docs = subprocess.run(docs_cmd, capture_output=True, text=True, timeout=600)
    return json.dumps({
        "ok": graph.returncode == 0 and docs.returncode == 0,
        "github_url": github_url,
        "graph_returncode": graph.returncode,
        "docs_returncode": docs.returncode,
        "graph_stdout": graph.stdout[-2000:],
        "graph_stderr": graph.stderr[-1000:],
        "docs_stdout": docs.stdout[-2000:],
        "docs_stderr": docs.stderr[-1000:],
    })


def get_tools() -> list[CustomToolDef]:
    return [
        (QueryContextInput, _query_context),
        (GetGraphOverviewInput, _get_graph_overview),
        (GetFileDependenciesInput, _get_file_dependencies),
        (GetCommitHistoryInput, _get_commit_history),
        (UpdateGraphInput, _update_graph),
    ]
