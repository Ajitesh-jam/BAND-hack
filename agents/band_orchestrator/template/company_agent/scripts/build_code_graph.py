"""Build codebase dependency graph from GitHub repo and/or docs/."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import UTC, datetime
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

        sample = "\n".join(
            f"- {n['path']} ({n.get('layer', 'core')})" for n in nodes[:40]
        )
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
    except Exception:  # noqa: BLE001
        return architecture_summary


def _count_cloned_files(repo_path: Path) -> dict[str, int | dict]:
    """Count all files in clone vs scannable source files for logging."""
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
    scannable_exts = sorted(_SOURCE_EXTENSIONS)
    top_ext = dict(sorted(by_ext.items(), key=lambda kv: kv[1], reverse=True)[:12])
    return {
        "total_files": total,
        "source_files": len(source_files),
        "scannable_extensions": scannable_exts,
        "top_extensions": top_ext,
    }


def build_code_graph(*, agent_root: Path, github_url: str | None = None) -> dict:
    global STEPS
    STEPS = []
    root = agent_root.resolve()
    logger = _setup_logger(root)
    log_path = str(root / "data" / "build_code_graph.log")

    docs_dir = root / "docs"
    graphs: list[dict] = []
    warnings: list[str] = []
    tmp_dir = root / "tmp" / "github_repo"

    _step(f"Starting code graph build for agent at {root}", logger=logger)

    if github_url:
        _step(f"GitHub URL provided: {github_url}", logger=logger)
        try:
            from band.tools import github_ops

            if tmp_dir.exists():
                _step(f"Removing previous temp clone at {tmp_dir}", logger=logger)
                shutil.rmtree(tmp_dir, ignore_errors=True)

            tmp_dir.parent.mkdir(parents=True, exist_ok=True)
            _step(f"Cloning repository into {tmp_dir}", logger=logger)
            clone = github_ops.clone_public_repo(github_url, dest=tmp_dir)
            if clone.get("ok") and clone.get("path"):
                repo_path = Path(clone["path"])
                _step(
                    f"Clone succeeded (mode={clone.get('mode')}, repo={clone.get('repo')})",
                    logger=logger,
                )
                stats = _count_cloned_files(repo_path)
                _step(
                    f"Clone contains {stats['total_files']} total files, "
                    f"{stats['source_files']} scannable source files "
                    f"(extensions: {', '.join(stats['scannable_extensions'])})",
                    logger=logger,
                )
                if stats["top_extensions"]:
                    _step(f"Top file types in clone: {stats['top_extensions']}", logger=logger)
                _step("Scanning cloned files and building dependency graph", logger=logger)
                repo_graph = build_graph_from_repo(repo_path)
                repo_graph["clone_stats"] = stats
                node_count = len(repo_graph.get("nodes", []))
                edge_count = len(repo_graph.get("edges", []))
                _step(
                    f"Graph from codebase: {node_count} nodes, {edge_count} edges",
                    logger=logger,
                )
                graphs.append(repo_graph)
            else:
                err = clone.get("error", "github clone failed")
                warnings.append(err)
                _step(f"Clone failed: {err}", logger=logger)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"github clone failed: {exc}")
            _step(f"Clone exception: {exc}", logger=logger)
        finally:
            if tmp_dir.exists():
                _step(f"Deleting temp clone at {tmp_dir}", logger=logger)
                shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        _step("No GitHub URL provided — skipping repo clone", logger=logger)

    if docs_dir.exists() and any(docs_dir.iterdir()):
        _step("Building supplemental graph from docs/", logger=logger)
        graphs.append(build_graph_from_docs(docs_dir))
    elif not github_url:
        msg = "no github URL and docs/ is empty — graph will be minimal"
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
    _step("Enriching architecture summary", logger=logger)
    merged["architecture_summary"] = _gemini_summarize(
        merged.get("nodes", []), merged.get("architecture_summary", "")
    )
    merged["warnings"] = warnings
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
        "clone_stats": next(
            (g.get("clone_stats") for g in graphs if g.get("clone_stats")), None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build codebase dependency graph.")
    parser.add_argument(
        "--agent-root",
        type=Path,
        default=AGENT_ROOT,
        help="Root folder of the company context agent.",
    )
    parser.add_argument(
        "--github-url",
        default=None,
        help="Optional public GitHub repository URL to clone and analyze.",
    )
    args = parser.parse_args()
    result = build_code_graph(agent_root=args.agent_root, github_url=args.github_url)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
