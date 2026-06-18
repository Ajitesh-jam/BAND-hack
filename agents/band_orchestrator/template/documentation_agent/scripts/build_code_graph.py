"""Build queryable and visual codebase graphs plus commit-history context."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))


def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "band").is_dir():
            return candidate
    return start


REPO_ROOT = _find_repo_root(AGENT_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_core.code_graph import (  # noqa: E402
    build_graph_from_docs,
    build_graph_from_repo,
    merge_graphs,
    save_commit_graph,
    save_graph,
)

STEPS: list[str] = []


def _step(msg: str, *, logger: logging.Logger) -> None:
    line = f"[{datetime.now(UTC).isoformat()}] {msg}"
    STEPS.append(line)
    logger.info(msg)
    print(line, flush=True)


def _setup_logger(agent_root: Path) -> logging.Logger:
    log_path = agent_root / "data" / "build_code_graph.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("build_code_graph")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def _gemini_summarize(nodes: list[dict], architecture_summary: str) -> str:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key or not nodes:
        return architecture_summary
    try:
        from google import genai
        from google.genai import types

        sample = "\n".join(f"- {n['path']} ({n.get('layer', 'core')})" for n in nodes[:60])
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                "Summarize this codebase architecture in 3-5 sentences for incident responders.\n\n"
                f"Current summary: {architecture_summary}\n\nFiles:\n{sample}"
            ),
            config=types.GenerateContentConfig(max_output_tokens=512, temperature=0.1),
        )
        text = (response.text or "").strip()
        return text or architecture_summary
    except Exception:
        return architecture_summary


def _count_cloned_files(repo_path: Path) -> dict[str, object]:
    from agent_core.code_graph import _SKIP_DIRS, _SOURCE_EXTENSIONS, walk_codebase

    total = 0
    by_ext: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name.startswith("."):
                continue
            total += 1
            ext = Path(name).suffix.lower() or "(no ext)"
            by_ext[ext] = by_ext.get(ext, 0) + 1
    source_files = walk_codebase(repo_path)
    return {
        "total_files": total,
        "source_files": len(source_files),
        "scannable_extensions": sorted(_SOURCE_EXTENSIONS),
        "top_extensions": dict(sorted(by_ext.items(), key=lambda kv: kv[1], reverse=True)[:12]),
    }


def _run_code2flow(repo_path: Path, agent_root: Path, logger: logging.Logger) -> dict[str, object]:
    data_dir = agent_root / "data"
    dot_path = data_dir / "code_graph.gv"
    svg_path = data_dir / "code_graph.svg"
    warnings: list[str] = []

    code2flow = shutil.which("code2flow")
    if not code2flow:
        warnings.append("code2flow executable not found; visual graph skipped")
        _step("code2flow executable not found; visual graph skipped", logger=logger)
        return {"ok": False, "warnings": warnings}

    _step(f"Running code2flow visualization into {dot_path}", logger=logger)
    result = subprocess.run(
        [code2flow, str(repo_path), "--output", str(dot_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        warnings.append(result.stderr.strip() or "code2flow failed")
        _step(f"code2flow failed: {warnings[-1]}", logger=logger)
        return {"ok": False, "warnings": warnings, "stderr": result.stderr[-1000:]}

    dot = shutil.which("dot")
    if dot:
        _step(f"Rendering SVG visualization into {svg_path}", logger=logger)
        svg = subprocess.run(
            [dot, "-Tsvg", str(dot_path), "-o", str(svg_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if svg.returncode != 0:
            warnings.append(svg.stderr.strip() or "Graphviz SVG render failed")
    else:
        warnings.append("graphviz dot executable not found; SVG render skipped")

    return {
        "ok": True,
        "dot_path": str(dot_path) if dot_path.exists() else None,
        "svg_path": str(svg_path) if svg_path.exists() else None,
        "warnings": warnings,
    }


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120)


def _build_commit_graph(repo_path: Path, agent_root: Path, repo: str | None, logger: logging.Logger) -> dict:
    _step("Building commit-history graph from git log", logger=logger)
    log = _git(["log", "--max-count=50", "--name-only", "--pretty=format:%H%x1f%an%x1f%ad%x1f%s", "--date=iso"], repo_path)
    commits: list[dict[str, object]] = []
    if log.returncode != 0:
        payload = {"ok": False, "repo": repo, "commits": [], "warning": log.stderr.strip()}
        save_commit_graph(payload, agent_root=agent_root)
        return payload

    current: dict[str, object] | None = None
    for raw in log.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "\x1f" in line:
            if current:
                commits.append(current)
            sha, author, date, subject = line.split("\x1f", 3)
            current = {"sha": sha, "author": author, "date": date, "subject": subject, "files": []}
        elif current is not None:
            current.setdefault("files", []).append(line)
    if current:
        commits.append(current)

    edge_counts: dict[tuple[str, str], int] = {}
    for commit in commits:
        files = sorted(set(commit.get("files", [])))
        for left, right in combinations(files, 2):
            edge_counts[(left, right)] = edge_counts.get((left, right), 0) + 1
    cochange_edges = [
        {"from": left, "to": right, "count": count}
        for (left, right), count in sorted(edge_counts.items(), key=lambda item: item[1], reverse=True)
    ]
    payload = {
        "ok": True,
        "repo": repo,
        "commit_count": len(commits),
        "commits": commits,
        "cochange_edges": cochange_edges,
    }
    save_commit_graph(payload, agent_root=agent_root)
    _step(f"Commit graph: {len(commits)} commits, {len(cochange_edges)} co-change edges", logger=logger)
    return payload


def build_code_graph(*, agent_root: Path, github_url: str | None = None) -> dict:
    global STEPS
    STEPS = []
    root = agent_root.resolve()
    logger = _setup_logger(root)
    log_path = str(root / "data" / "build_code_graph.log")

    docs_dir = root / "docs"
    graphs: list[dict] = []
    warnings: list[str] = []
    visualization: dict[str, object] = {}
    commit_graph: dict[str, object] = {}
    clone_stats: dict[str, object] | None = None
    repo_path: Path | None = None

    _step(f"Starting code graph build for agent at {root}", logger=logger)

    if github_url:
        _step(f"GitHub URL provided: {github_url}", logger=logger)
        try:
            from band.tools import github_ops

            shared_path = github_ops._working_repo_path()
            _step(f"Ensuring shared workspace clone at {shared_path}", logger=logger)
            clone = github_ops.ensure_working_repo(github_url)
            if clone.get("ok") and clone.get("path"):
                repo_path = Path(clone["path"])
                _step(
                    f"Shared clone ready (mode={clone.get('mode')}, repo={clone.get('repo')}) "
                    f"at {repo_path}",
                    logger=logger,
                )
                clone_stats = _count_cloned_files(repo_path)
                _step(
                    f"Clone contains {clone_stats['total_files']} total files, "
                    f"{clone_stats['source_files']} scannable source files",
                    logger=logger,
                )
                _step(f"Top file types in clone: {clone_stats['top_extensions']}", logger=logger)
                visualization = _run_code2flow(repo_path, root, logger)
                warnings.extend(visualization.get("warnings", []))
                _step("Scanning shared workspace and building queryable dependency graph", logger=logger)
                repo_graph = build_graph_from_repo(repo_path)
                repo_graph["clone_stats"] = clone_stats
                repo_graph["workspace_path"] = str(repo_path)
                graphs.append(repo_graph)
                commit_graph = _build_commit_graph(repo_path, root, clone.get("repo"), logger)
                if not commit_graph.get("ok"):
                    warnings.append(str(commit_graph.get("warning", "commit graph failed")))
                _step(
                    f"Graph from codebase: {len(repo_graph.get('nodes', []))} nodes, "
                    f"{len(repo_graph.get('edges', []))} edges",
                    logger=logger,
                )
            else:
                err = clone.get("error", "github clone failed")
                warnings.append(err)
                _step(f"Clone failed: {err}", logger=logger)
        except Exception as exc:
            warnings.append(f"github clone failed: {exc}")
            _step(f"Clone exception: {exc}", logger=logger)
    else:
        _step("No GitHub URL provided; skipping repo clone", logger=logger)

    if docs_dir.exists() and any(docs_dir.iterdir()):
        _step("Building supplemental graph from docs/", logger=logger)
        graphs.append(build_graph_from_docs(docs_dir))
    elif not github_url:
        msg = "no github URL and docs/ is empty; graph will be minimal"
        warnings.append(msg)
        _step(msg, logger=logger)

    if not graphs:
        graphs.append({
            "nodes": [],
            "edges": [],
            "architecture_summary": "No graph data available. Add docs or provide a GitHub URL.",
            "file_tree": {},
            "source": "none",
        })

    merged = merge_graphs(*graphs)
    merged["architecture_summary"] = _gemini_summarize(
        merged.get("nodes", []), merged.get("architecture_summary", "")
    )
    merged["warnings"] = warnings
    merged["visualization"] = visualization
    graph_path = save_graph(merged, agent_root=root)
    _step(f"Saved graph to {graph_path}", logger=logger)
    _step("Code graph build complete", logger=logger)

    return {
        "ok": True,
        "graph_path": graph_path,
        "log_path": log_path,
        "node_count": len(merged.get("nodes", [])),
        "edge_count": len(merged.get("edges", [])),
        "source": merged.get("source"),
        "warnings": warnings,
        "steps": STEPS,
        "github_url": github_url,
        "workspace_path": str(repo_path) if repo_path else None,
        "clone_stats": clone_stats,
        "visualization": visualization,
        "commit_graph": {
            "ok": commit_graph.get("ok"),
            "commit_count": commit_graph.get("commit_count", 0),
            "cochange_edge_count": len(commit_graph.get("cochange_edges", [])),
            "path": str(root / "data" / "commit_graph.json"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build codebase dependency graph.")
    parser.add_argument("--agent-root", type=Path, default=AGENT_ROOT)
    parser.add_argument("--github-url", default=None)
    args = parser.parse_args()
    result = build_code_graph(agent_root=args.agent_root, github_url=args.github_url)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
