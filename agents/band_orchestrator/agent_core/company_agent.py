"""Scaffold, index, and deploy company code-context agents from template."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import yaml

from band.config import ROOT_DIR

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "template" / "company_agent"
GENERATED_DIR = ROOT_DIR / "generated_agents"


def _unique_dir(slug: str) -> Path:
    return GENERATED_DIR / f"{slug}_{uuid.uuid4().hex[:8]}"


def _resolve_agent_folder(name: str) -> Path | None:
    direct = GENERATED_DIR / name
    if direct.exists():
        return direct
    matches = sorted(GENERATED_DIR.glob(f"{name}_*"))
    if matches:
        return matches[-1]
    if Path(name).exists():
        return Path(name)
    return None


def _python_cmd(script: Path, agent_folder: Path, extra_args: list[str] | None = None) -> list[str]:
    """Prefer ``uv run python`` so project deps (sentence-transformers) are available."""
    args = ["--agent-root", str(agent_folder), *(extra_args or [])]
    uv_bin = shutil.which("uv")
    if uv_bin and (ROOT_DIR / "pyproject.toml").exists():
        return [uv_bin, "run", "--directory", str(ROOT_DIR), "python", str(script), *args]
    return [sys.executable, str(script), *args]


def _build_env(agent_folder: Path) -> dict[str, str]:
    env = dict(os.environ)
    parts = [str(agent_folder), str(ROOT_DIR), env.get("PYTHONPATH", "")]
    env["PYTHONPATH"] = os.pathsep.join(p for p in parts if p)
    return env


def _run_build_script(
    script: Path,
    *,
    agent_folder: Path,
    extra_args: list[str] | None = None,
    log_name: str,
) -> dict:
    cmd = _python_cmd(script, agent_folder, extra_args)

    build_log = agent_folder / "data" / f"{log_name}.log"
    build_log.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Running %s", " ".join(cmd))
    with build_log.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n--- build invoked: {' '.join(cmd)} ---\n")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=_build_env(agent_folder),
            cwd=str(ROOT_DIR),
            timeout=600,
        )
        log_file.write(result.stdout)
        if result.stderr:
            log_file.write("\n[stderr]\n")
            log_file.write(result.stderr)

    parsed: dict = {}
    stdout = result.stdout.strip()
    if stdout:
        # Script prints step logs then JSON — parse the last JSON object in stdout.
        decoder = json.JSONDecoder()
        for i, ch in enumerate(stdout):
            if ch == "{":
                try:
                    parsed, _ = decoder.raw_decode(stdout[i:])
                except json.JSONDecodeError:
                    continue
        if not parsed:
            parsed = {"raw_output": result.stdout[-2000:]}

    ok = result.returncode == 0
    return {
        "ok": ok,
        "returncode": result.returncode,
        "log_path": str(build_log),
        "stdout": result.stdout[-3000:],
        "stderr": result.stderr[-1000:],
        "result": parsed,
    }


def scaffold_company_agent(
    agent_id: str,
    api_key: str,
    name: str | None = None,
) -> dict:
    """Copy template to generated_agents/ and write agent_config.yaml."""
    slug = name or "company_context"
    folder = _unique_dir(slug)
    if not TEMPLATE_DIR.exists():
        return {"ok": False, "error": f"template not found: {TEMPLATE_DIR}"}

    shutil.copytree(
        TEMPLATE_DIR,
        folder,
        ignore=shutil.ignore_patterns("data/*", "__pycache__", "tmp/*"),
    )
    (folder / "data").mkdir(parents=True, exist_ok=True)
    (folder / "docs").mkdir(parents=True, exist_ok=True)
    (folder / "tmp").mkdir(parents=True, exist_ok=True)

    config = {
        "agent": {
            "name": folder.name,
            "agent_id": agent_id,
            "api_key": api_key,
        }
    }
    (folder / "agent_config.yaml").write_text(
        yaml.safe_dump(config, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    docs_path = folder / "docs"
    return {
        "ok": True,
        "name": folder.name,
        "folder": str(folder),
        "main_path": str(folder / "main.py"),
        "agent_id": agent_id,
        "docs_path": str(docs_path),
        "next_step": (
            f"Add documentation files to {docs_path}, then call buildcompanycontext "
            f"with name={folder.name} and optional github_url."
        ),
    }


def _sync_template_modules(folder: Path) -> None:
    """Refresh build scripts and graph/RAG modules from template before rebuild."""
    for rel in (
        "scripts/build_code_graph.py",
        "scripts/build_docs_rag.py",
        "agent_core/code_graph.py",
        "agent_core/docs_rag.py",
        "agent_core/embedding.py",
    ):
        src = TEMPLATE_DIR / rel
        dst = folder / rel
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def build_company_context(name: str, github_url: str | None = None) -> dict:
    """Run build_code_graph.py and build_docs_rag.py for a scaffolded agent."""
    folder = _resolve_agent_folder(name)
    if not folder:
        return {"ok": False, "error": f"unknown company context agent '{name}'"}

    _sync_template_modules(folder)
    graph_script = folder / "scripts" / "build_code_graph.py"
    docs_script = folder / "scripts" / "build_docs_rag.py"
    warnings: list[str] = []
    steps: list[str] = []
    graph_built = False
    docs_indexed = False
    graph_details: dict = {}
    docs_details: dict = {}

    if graph_script.exists():
        extra = ["--github-url", github_url] if github_url else []
        graph_run = _run_build_script(
            graph_script,
            agent_folder=folder,
            extra_args=extra,
            log_name="build_company_context",
        )
        graph_built = graph_run["ok"]
        graph_details = graph_run.get("result", {})
        if graph_details.get("steps"):
            steps.extend(graph_details["steps"])
        if not graph_built:
            warnings.append(graph_run.get("stderr") or "build_code_graph failed")
        else:
            logger.info(
                "Graph build: nodes=%s edges=%s log=%s",
                graph_details.get("node_count"),
                graph_details.get("edge_count"),
                graph_run.get("log_path"),
            )
    else:
        warnings.append("build_code_graph.py missing")

    if docs_script.exists():
        docs_run = _run_build_script(
            docs_script,
            agent_folder=folder,
            log_name="build_docs_rag",
        )
        docs_indexed = docs_run["ok"]
        docs_details = docs_run.get("result", {})
        if not docs_indexed:
            warnings.append(docs_run.get("stderr") or "build_docs_rag failed")
        else:
            logger.info("Docs RAG build log: %s", docs_run.get("log_path"))
    else:
        warnings.append("build_docs_rag.py missing")

    return {
        "ok": graph_built or docs_indexed,
        "name": folder.name,
        "folder": str(folder),
        "graph_built": graph_built,
        "docs_indexed": docs_indexed,
        "graph": graph_details,
        "docs": docs_details,
        "github_url": github_url,
        "steps": steps,
        "warnings": warnings,
        "log_paths": {
            "graph": str(folder / "data" / "build_code_graph.log"),
            "build": str(folder / "data" / "build_company_context.log"),
            "docs": str(folder / "data" / "build_docs_rag.log"),
        },
        "next_step": f"Call deploycompanycontextagent with name={folder.name}",
    }


def deploy_company_agent(name: str) -> dict:
    """Return metadata needed to spawn the company context agent."""
    folder = _resolve_agent_folder(name)
    if not folder:
        return {"ok": False, "error": f"unknown company context agent '{name}'"}
    main_path = folder / "main.py"
    if not main_path.exists():
        return {"ok": False, "error": f"main.py not found in {folder}"}

    creds = yaml.safe_load((folder / "agent_config.yaml").read_text(encoding="utf-8")) or {}
    agent_id = creds.get("agent", {}).get("agent_id")
    return {
        "ok": True,
        "name": folder.name,
        "folder": str(folder),
        "main_path": str(main_path),
        "agent_id": agent_id,
    }
