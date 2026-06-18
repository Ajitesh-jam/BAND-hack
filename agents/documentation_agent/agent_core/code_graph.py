"""Code dependency graph — build, query, and impact analysis."""

from __future__ import annotations

import ast
import json
import os
import re
from collections import deque
from pathlib import Path
from typing import Any

AGENT_ROOT = Path(__file__).resolve().parent.parent

_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".workspace", "generated_agents", ".cursor",
}
_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".ico", ".zip", ".tar", ".gz", ".whl", ".lock",
}
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".sol", ".cairo", ".vy", ".c", ".cpp", ".h", ".hpp", ".md", ".yaml", ".yml", ".toml",
}
_MAX_FILES = 500


def _agent_path(rel: str, agent_root: Path | None = None) -> Path:
    root = agent_root or AGENT_ROOT
    return root / rel


def _is_skipped(path: Path, repo_root: Path | None = None) -> bool:
    parts = path.parts
    if repo_root is not None:
        try:
            parts = path.relative_to(repo_root.resolve()).parts
        except ValueError:
            pass
    for part in parts:
        if part in _SKIP_DIRS:
            return True
    if path.suffix.lower() in _SKIP_EXTENSIONS:
        return True
    return False


def walk_codebase(root: Path) -> list[Path]:
    files: list[Path] = []
    if not root.exists():
        return files
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if _is_skipped(path, root):
                continue
            if path.suffix.lower() in _SOURCE_EXTENSIONS:
                files.append(path)
            if len(files) >= _MAX_FILES:
                return files
    return files


def _python_imports(path: Path, root: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.replace(".", "/"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.replace(".", "/"))
    rel = str(path.relative_to(root))
    resolved: list[str] = []
    for imp in imports:
        candidate = root / f"{imp}.py"
        if candidate.exists():
            resolved.append(str(candidate.relative_to(root)))
        else:
            pkg_init = root / imp / "__init__.py"
            if pkg_init.exists():
                resolved.append(str(pkg_init.relative_to(root)))
    return resolved


def _js_imports(path: Path, root: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    imports: list[str] = []
    for match in re.finditer(r"(?:import|from)\s+['\"]([^'\"]+)['\"]", text):
        imports.append(match.group(1))
    for match in re.finditer(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", text):
        imports.append(match.group(1))
    resolved: list[str] = []
    base = path.parent
    for imp in imports:
        if imp.startswith("."):
            candidate = (base / imp).resolve()
            for ext in ("", ".js", ".ts", ".tsx", ".jsx"):
                p = Path(str(candidate) + ext)
                try:
                    rel = str(p.relative_to(root))
                    resolved.append(rel)
                    break
                except ValueError:
                    continue
    return resolved


def build_file_tree(root: Path, files: list[Path]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for path in files:
        rel = str(path.relative_to(root))
        parts = rel.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = "file"
    return tree


def _infer_layer(path: str) -> str:
    lower = path.lower()
    if "test" in lower:
        return "test"
    if any(x in lower for x in ("config", "settings", ".env")):
        return "config"
    if any(x in lower for x in ("api", "route", "handler", "controller")):
        return "api"
    if any(x in lower for x in ("model", "schema", "entity")):
        return "model"
    if any(x in lower for x in ("tool", "util", "helper", "lib")):
        return "utility"
    return "core"


def build_graph_from_repo(repo_root: Path) -> dict[str, Any]:
    files = walk_codebase(repo_root)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []

    for path in files:
        rel = str(path.relative_to(repo_root))
        nodes[rel] = {
            "id": rel,
            "path": rel,
            "summary": f"Source file ({path.suffix})",
            "layer": _infer_layer(rel),
        }

    for path in files:
        rel = str(path.relative_to(repo_root))
        if path.suffix == ".py":
            targets = _python_imports(path, repo_root)
        elif path.suffix in {".js", ".ts", ".tsx", ".jsx"}:
            targets = _js_imports(path, repo_root)
        else:
            targets = []
        for target in targets:
            if target in nodes:
                edges.append({"from": rel, "to": target, "kind": "import"})

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "architecture_summary": _summarize_architecture(nodes, edges),
        "file_tree": build_file_tree(repo_root, files),
        "source": "github",
    }


def _extract_paths_from_docs(docs_dir: Path) -> list[str]:
    paths: set[str] = set()
    pattern = re.compile(r"(?:[\w.-]+/)+[\w.-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|md|yaml|yml)")
    for path in docs_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in pattern.findall(text):
            paths.add(match.lstrip("./"))
    return sorted(paths)


def build_graph_from_docs(docs_dir: Path) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    doc_nodes: dict[str, dict[str, Any]] = {}

    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = str(path.relative_to(docs_dir.parent))
        heading = path.stem.replace("_", " ").replace("-", " ")
        doc_nodes[rel] = {
            "id": rel,
            "path": rel,
            "summary": f"Documentation: {heading}",
            "layer": "docs",
        }

    for doc_path in sorted(docs_dir.rglob("*")):
        if not doc_path.is_file():
            continue
        rel_doc = str(doc_path.relative_to(docs_dir.parent))
        text = doc_path.read_text(encoding="utf-8", errors="replace")
        for file_path in _extract_paths_from_docs(docs_dir):
            if file_path in text:
                nodes.append({
                    "id": file_path,
                    "path": file_path,
                    "summary": f"Mentioned in docs ({file_path})",
                    "layer": _infer_layer(file_path),
                })
                edges.append({"from": rel_doc, "to": file_path, "kind": "documents"})

    nodes.extend(doc_nodes.values())
    seen: set[str] = set()
    unique_nodes: list[dict[str, Any]] = []
    for n in nodes:
        if n["id"] not in seen:
            seen.add(n["id"])
            unique_nodes.append(n)

    return {
        "nodes": unique_nodes,
        "edges": edges,
        "architecture_summary": _summarize_architecture(
            {n["id"]: n for n in unique_nodes}, edges
        ),
        "file_tree": {},
        "source": "docs",
    }


def merge_graphs(*graphs: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    trees: list[dict[str, Any]] = []
    summaries: list[str] = []

    for graph in graphs:
        if not graph:
            continue
        for node in graph.get("nodes", []):
            nodes[node["id"]] = node
        edges.extend(graph.get("edges", []))
        if graph.get("file_tree"):
            trees.append(graph["file_tree"])
        if graph.get("architecture_summary"):
            summaries.append(graph["architecture_summary"])

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "architecture_summary": "\n\n".join(summaries) if summaries else "No architecture summary available.",
        "file_tree": trees[0] if trees else {},
        "source": "+".join({g.get("source", "unknown") for g in graphs if g}),
    }


def _summarize_architecture(nodes: dict[str, dict], edges: list[dict[str, str]]) -> str:
    if not nodes:
        return "No codebase graph available yet."
    layers: dict[str, int] = {}
    for node in nodes.values():
        layer = node.get("layer", "core")
        layers[layer] = layers.get(layer, 0) + 1
    layer_summary = ", ".join(f"{k}: {v} files" for k, v in sorted(layers.items()))
    import_edges = sum(1 for e in edges if e.get("kind") == "import")
    return (
        f"Codebase graph with {len(nodes)} nodes and {len(edges)} edges "
        f"({import_edges} import dependencies). Layers: {layer_summary}."
    )


def _load_graph(agent_root: Path | None = None) -> dict[str, Any] | None:
    root = agent_root or AGENT_ROOT
    graph_path = root / "data" / "code_graph.json"
    if not graph_path.exists():
        return None
    return json.loads(graph_path.read_text(encoding="utf-8"))


def save_graph(graph: dict[str, Any], *, agent_root: Path | None = None) -> str:
    root = agent_root or AGENT_ROOT
    graph_path = root / "data" / "code_graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    return str(graph_path)


def query_graph(query: str, *, agent_root: Path | None = None) -> dict[str, Any]:
    graph = _load_graph(agent_root)
    if not graph:
        return {"ok": False, "matches": [], "neighborhood": [], "summary": ""}

    q_tokens = {
        t.lower() for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", query)
        if len(t) > 2
    }
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])

    scored: list[tuple[int, dict]] = []
    for node in graph.get("nodes", []):
        hay = f"{node.get('path', '')} {node.get('summary', '')}".lower()
        score = sum(1 for t in q_tokens if t in hay)
        if score:
            scored.append((score, node))
    scored.sort(key=lambda x: x[0], reverse=True)
    matches = [n for _, n in scored[:10]]

    match_ids = {m["id"] for m in matches}
    neighborhood: list[dict] = []
    adj: dict[str, set[str]] = {}
    for e in edges:
        adj.setdefault(e["from"], set()).add(e["to"])
        adj.setdefault(e["to"], set()).add(e["from"])

    visited: set[str] = set()
    queue: deque[str] = deque(match_ids)
    while queue and len(neighborhood) < 20:
        nid = queue.popleft()
        if nid in visited or nid not in nodes:
            continue
        visited.add(nid)
        neighborhood.append(nodes[nid])
        for nb in adj.get(nid, set()):
            if nb not in visited:
                queue.append(nb)

    return {
        "ok": True,
        "matches": matches,
        "neighborhood": neighborhood,
        "summary": graph.get("architecture_summary", ""),
        "edge_count": len(edges),
        "node_count": len(nodes),
    }


def get_graph_overview(*, agent_root: Path | None = None) -> dict[str, Any]:
    graph = _load_graph(agent_root)
    if not graph:
        return {"ok": False, "error": "code graph not built yet"}
    root = agent_root or AGENT_ROOT
    data_dir = root / "data"
    mermaid_edges = [
        f"  {e['from'].replace('/', '_').replace('.', '_')} --> {e['to'].replace('/', '_').replace('.', '_')}"
        for e in graph.get("edges", [])[:30]
    ]
    return {
        "ok": True,
        "architecture_summary": graph.get("architecture_summary", ""),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        "file_tree": graph.get("file_tree", {}),
        "mermaid_sample": "graph LR\n" + "\n".join(mermaid_edges) if mermaid_edges else "",
        "source": graph.get("source", "unknown"),
        "visualization": {
            "dot": str(data_dir / "code_graph.gv") if (data_dir / "code_graph.gv").exists() else None,
            "svg": str(data_dir / "code_graph.svg") if (data_dir / "code_graph.svg").exists() else None,
        },
    }


def get_file_dependencies(file_path: str, *, agent_root: Path | None = None) -> dict[str, Any]:
    graph = _load_graph(agent_root)
    if not graph:
        return {"ok": False, "error": "code graph not built yet"}

    normalized = file_path.lstrip("./")
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    if normalized not in nodes:
        for nid in nodes:
            if nid.endswith(normalized) or normalized.endswith(nid):
                normalized = nid
                break

    downstream: set[str] = set()
    upstream: set[str] = set()
    for e in graph.get("edges", []):
        if e["from"] == normalized:
            downstream.add(e["to"])
        if e["to"] == normalized:
            upstream.add(e["from"])

    impact = sorted(downstream | upstream)
    return {
        "ok": True,
        "file": normalized,
        "imports": sorted(downstream),
        "imported_by": sorted(upstream),
        "impact_files": impact,
        "node": nodes.get(normalized),
    }


def save_commit_graph(payload: dict[str, Any], *, agent_root: Path | None = None) -> str:
    root = agent_root or AGENT_ROOT
    graph_path = root / "data" / "commit_graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(graph_path)


def get_commit_history(
    query: str | None = None,
    *,
    limit: int = 10,
    agent_root: Path | None = None,
) -> dict[str, Any]:
    root = agent_root or AGENT_ROOT
    graph_path = root / "data" / "commit_graph.json"
    if not graph_path.exists():
        return {"ok": False, "error": "commit graph not built yet", "commits": []}

    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    commits = payload.get("commits", [])
    if query:
        q_tokens = {
            t.lower() for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", query)
            if len(t) > 2
        }
        scored: list[tuple[int, dict[str, Any]]] = []
        for commit in commits:
            hay = " ".join([
                commit.get("sha", ""),
                commit.get("subject", ""),
                " ".join(commit.get("files", [])),
            ]).lower()
            score = sum(1 for token in q_tokens if token in hay)
            if score:
                scored.append((score, commit))
        scored.sort(key=lambda item: item[0], reverse=True)
        commits = [commit for _, commit in scored]

    return {
        "ok": True,
        "repo": payload.get("repo"),
        "commit_count": payload.get("commit_count", len(payload.get("commits", []))),
        "cochange_edges": payload.get("cochange_edges", [])[:50],
        "commits": commits[:limit],
    }
