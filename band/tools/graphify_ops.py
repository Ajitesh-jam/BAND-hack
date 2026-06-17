"""Graphify CLI wrappers for code graph build and query."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from band.config import ROOT_DIR


def resolve_target(path: str | None = None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    return ROOT_DIR / "demo-app"


def graphify_out_dir(target: Path) -> Path:
    return target / "graphify-out"


def graph_json_path(target: Path) -> Path:
    return graphify_out_dir(target) / "graph.json"


def context_paths(target_path: str | None = None) -> dict[str, str]:
    """Return graphify-out and docs paths for orchestrator handoff."""
    target = resolve_target(target_path)
    docs_root = ROOT_DIR / "agents" / "company_agent"
    return {
        "target_path": str(target),
        "graph_dir": str(graphify_out_dir(target)),
        "graph_json": str(graph_json_path(target)),
        "graph_report": str(graphify_out_dir(target) / "GRAPH_REPORT.md"),
        "docs_dir": str(docs_root / "docs"),
        "docs_index": str(docs_root / "data" / "docs_index.json"),
    }


def _run_graphify(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    graphify = shutil.which("graphify")
    if not graphify:
        return {"ok": False, "error": "graphify CLI not found — install from https://github.com/graphify"}

    try:
        result = subprocess.run(
            [graphify, *args],
            capture_output=True,
            text=True,
            cwd=str(cwd or ROOT_DIR),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"graphify timed out after {timeout}s"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-2000:],
    }


def build_graph(target_path: str | None = None) -> dict[str, Any]:
    """Run `graphify update` on the target codebase (AST-only, no LLM)."""
    target = resolve_target(target_path)
    if not target.exists():
        return {"ok": False, "error": f"target not found: {target}"}

    run = _run_graphify(["update", str(target)])
    overview = graph_overview(target_path=str(target))
    return {
        **run,
        "target": str(target),
        "graph_dir": str(graphify_out_dir(target)),
        "overview": overview,
    }


def _load_graph(target: Path) -> dict[str, Any] | None:
    path = graph_json_path(target)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def graph_overview(target_path: str | None = None) -> dict[str, Any]:
    """Return file/node/edge/community counts from graphify-out/graph.json."""
    target = resolve_target(target_path)
    graph = _load_graph(target)
    if not graph:
        return {"ok": False, "error": f"no graph at {graph_json_path(target)} — run build_graph first"}

    nodes = graph.get("nodes") or []
    links = graph.get("links") or graph.get("edges") or []
    file_nodes = [n for n in nodes if n.get("file_type") == "code" or str(n.get("source_file", "")).endswith(".py")]
    communities = {n.get("community") for n in nodes if n.get("community") is not None}

    return {
        "ok": True,
        "target": str(target),
        "files": len(file_nodes) or len(nodes),
        "nodes": len(nodes),
        "edges": len(links),
        "communities": len(communities),
        "graph_dir": str(graphify_out_dir(target)),
    }


def query_graph(question: str, target_path: str | None = None) -> dict[str, Any]:
    """Run `graphify query` for scoped subgraph context."""
    target = resolve_target(target_path)
    run = _run_graphify(["query", question, "--budget", "800"], cwd=target.parent if target.is_file() else target)
    return {**run, "question": question, "target": str(target)}


def file_dependencies(relative_path: str, target_path: str | None = None) -> dict[str, Any]:
    """Find dependents and dependencies for a file via graphify query."""
    target = resolve_target(target_path)
    rel = relative_path.lstrip("/")
    stem = Path(rel).stem.replace("_", " ")
    query = f"dependencies and callers of {rel} {stem}"
    run = query_graph(query, target_path=str(target))

    graph = _load_graph(target)
    deps: list[str] = []
    dependents: list[str] = []
    if graph:
        node_id = None
        for node in graph.get("nodes") or []:
            src = str(node.get("source_file", ""))
            if src == rel or src.endswith(f"/{rel}"):
                node_id = node.get("id")
                break
        if node_id:
            for link in graph.get("links") or []:
                if link.get("target") == node_id:
                    deps.append(_node_label(graph, link.get("source", "")))
                if link.get("source") == node_id:
                    dependents.append(_node_label(graph, link.get("target", "")))

    return {
        **run,
        "relative_path": rel,
        "dependencies": deps[:20],
        "dependents": dependents[:20],
    }


def _node_label(graph: dict[str, Any], node_id: str) -> str:
    for node in graph.get("nodes") or []:
        if node.get("id") == node_id:
            return str(node.get("source_file") or node.get("label") or node_id)
    return str(node_id)


def read_architecture_summary(target_path: str | None = None) -> dict[str, Any]:
    """Return GRAPH_REPORT.md excerpt if present."""
    target = resolve_target(target_path)
    report = graphify_out_dir(target) / "GRAPH_REPORT.md"
    if not report.exists():
        return {"ok": False, "error": f"no report at {report}"}
    text = report.read_text(encoding="utf-8", errors="replace")
    return {"ok": True, "report_path": str(report), "summary": text[:6000]}
