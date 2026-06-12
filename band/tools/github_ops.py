"""Git and GitHub operations for fix engineer and reviewer."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from band.config import get_settings


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.returncode == 0,
    }


def _workspace() -> Path:
    settings = get_settings()
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    return settings.workspace_dir


def _repo_slug() -> str | None:
    """e.g. kalki-kgp/bandaid-demo-app from DEMO_APP_REPO URL."""
    url = get_settings().demo_app_repo.rstrip("/")
    if "github.com/" not in url:
        return None
    return url.split("github.com/", 1)[-1].removesuffix(".git")


def _gh_env() -> dict[str, str]:
    env: dict[str, str] = {}
    token = get_settings().demo_app_github_token
    if token:
        env["GH_TOKEN"] = token
    return env


def _gh_pr_cmd(subcommand: str, *args: str) -> list[str]:
    """Build `gh pr <subcommand> [--repo slug] ...` with explicit repo when configured."""
    cmd = ["gh", "pr", subcommand, *args]
    repo = _repo_slug()
    if repo:
        return cmd[:3] + ["--repo", repo] + cmd[3:]
    return cmd


def _default_branch_from_git(cwd: Path) -> str | None:
    """Read default branch from local clone (origin HEAD)."""
    remote = _run(["git", "remote", "show", "origin"], cwd=cwd)
    if not remote["ok"]:
        return None
    for line in remote["stdout"].splitlines():
        line = line.strip()
        if line.startswith("HEAD branch:"):
            return line.split(":", 1)[1].strip()
    return None


def default_branch() -> str:
    """Resolve the repo default branch — never guess main vs master."""
    repo = _repo_slug()
    env = _gh_env()

    if repo:
        result = _run(
            [
                "gh",
                "repo",
                "view",
                repo,
                "--json",
                "defaultBranchRef",
                "-q",
                ".defaultBranchRef.name",
            ],
            env=env,
        )
        if result["ok"] and result["stdout"].strip():
            return result["stdout"].strip()

    settings = get_settings()
    if settings.demo_app_repo:
        target = _workspace() / "demo-app"
        if target.exists():
            branch = _default_branch_from_git(target)
            if branch:
                return branch
    else:
        local = Path(__file__).resolve().parent.parent.parent / "demo-app"
        if local.exists():
            branch = _default_branch_from_git(local)
            if branch:
                return branch

    return "main"


def get_repo_info() -> dict[str, Any]:
    """Return repo slug and detected default branch for agents before git/gh commands."""
    slug = _repo_slug()
    branch = default_branch()
    return {"ok": True, "repo": slug, "default_branch": branch}


def clone_or_pull_repo() -> dict[str, Any]:
    """Clone demo-app repo or pull latest changes."""
    settings = get_settings()
    repo_url = settings.demo_app_repo
    if not repo_url:
        # Fall back to local demo-app directory for hackathon demos without remote
        local = Path(__file__).resolve().parent.parent.parent / "demo-app"
        return {"ok": True, "path": str(local), "mode": "local"}

    target = _workspace() / "demo-app"
    token = settings.demo_app_github_token
    if token and repo_url.startswith("https://"):
        repo_url = repo_url.replace("https://", f"https://{token}@")

    if target.exists():
        pull = _run(["git", "pull", "--rebase"], cwd=target)
        return {**pull, "path": str(target), "default_branch": default_branch(), "repo": _repo_slug()}

    clone = _run(["git", "clone", repo_url, str(target)])
    return {**clone, "path": str(target), "default_branch": default_branch(), "repo": _repo_slug()}


def create_branch(branch_name: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.demo_app_repo:
        local = Path(__file__).resolve().parent.parent.parent / "demo-app"
        return {"ok": True, "path": str(local), "branch": branch_name, "mode": "local"}
    target = _workspace() / "demo-app"
    checkout = _run(["git", "checkout", "-b", branch_name], cwd=target)
    return {**checkout, "path": str(target), "branch": branch_name}


def write_file(relative_path: str, content: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.demo_app_repo:
        base = Path(__file__).resolve().parent.parent.parent / "demo-app"
    else:
        base = _workspace() / "demo-app"
    target = base / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"ok": True, "path": str(target)}


def commit_and_push(message: str, branch: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.demo_app_repo:
        return {"ok": True, "mode": "local", "message": "skipped push in local mode"}
    target = _workspace() / "demo-app"
    _run(["git", "add", "-A"], cwd=target)
    commit = _run(["git", "commit", "-m", message], cwd=target)
    if not commit["ok"] and "nothing to commit" in commit["stdout"] + commit["stderr"]:
        return {"ok": False, "error": "nothing to commit"}
    push = _run(["git", "push", "-u", "origin", branch], cwd=target)
    return {"commit": commit, "push": push, "ok": push["ok"]}


def open_pull_request(title: str, body: str, branch: str, base: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.demo_app_repo:
        return {
            "ok": True,
            "mode": "local",
            "pr_url": f"https://github.com/example/bandaid-demo/pull/local-{branch}",
            "title": title,
        }
    target = _workspace() / "demo-app"
    env = _gh_env()
    resolved_base = base or default_branch()
    existing = find_pull_request(branch)
    if existing.get("ok") and existing.get("pr_url"):
        return {**existing, "already_exists": True, "base": resolved_base}

    cmd = _gh_pr_cmd(
        "create",
        "--title",
        title,
        "--body",
        body,
        "--head",
        branch,
        "--base",
        resolved_base,
    )
    result = _run(cmd, cwd=target, env=env)
    pr_url = result["stdout"].strip() if result["ok"] else None
    if not pr_url:
        pr_url = _pr_url_from_gh_output(result["stdout"], result["stderr"])
    if pr_url:
        result = {**result, "ok": True, "pr_url": pr_url}
        if "already exists" in result.get("stderr", ""):
            result["already_exists"] = True
    return {**result, "pr_url": pr_url, "base": resolved_base}


def extract_pr_number(text: str) -> str | None:
    match = re.search(r"pull[s]?/(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r"#(\d+)", text)
    return match.group(1) if match else None


def _pr_url_from_gh_output(stdout: str, stderr: str) -> str | None:
    for text in (stdout, stderr):
        match = re.search(r"https://github\.com/[^\s]+/pull/\d+", text)
        if match:
            return match.group(0).rstrip(".")
    return None


def find_pull_request(branch: str) -> dict[str, Any]:
    """Return an open PR for branch if one exists."""
    repo = _repo_slug()
    if not repo:
        return {"ok": False, "error": "no remote repo configured"}
    env = _gh_env()
    result = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch,
            "--json",
            "number,url,state",
            "--limit",
            "1",
        ],
        env=env,
    )
    if not result["ok"] or not result["stdout"].strip():
        return {**result, "ok": False}

    prs = json.loads(result["stdout"])
    if not prs:
        return {"ok": False, "error": "no pull request found"}
    pr = prs[0]
    return {
        "ok": True,
        "pr_url": pr["url"],
        "pr_number": pr["number"],
        "state": pr.get("state"),
    }


def fetch_pr_diff(pr_url_or_number: str) -> dict[str, Any]:
    settings = get_settings()
    pr_number = extract_pr_number(pr_url_or_number) or pr_url_or_number
    if not settings.demo_app_repo:
        # Return a placeholder diff for local demos
        return {
            "ok": True,
            "mode": "local",
            "diff": "--- a/app/main.py\n+++ b/app/main.py\n@@ -1,3 +1,3 @@\n-pool_size = 2\n+pool_size = 10\n",
        }
    env = _gh_env()
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(_gh_pr_cmd("diff", pr_number), cwd=Path(tmp), env=env)
    return {**result, "pr_number": pr_number}


def merge_pull_request(pr_url_or_number: str) -> dict[str, Any]:
    settings = get_settings()
    pr_number = extract_pr_number(pr_url_or_number) or pr_url_or_number
    if not settings.demo_app_repo:
        from band.tools.demo_app import clear_chaos

        clear_result = clear_chaos()
        return {"ok": True, "mode": "local", "merge": "simulated", "recovery": clear_result}
    env = _gh_env()
    merge = _run(_gh_pr_cmd("merge", pr_number, "--squash", "--delete-branch"), env=env)
    from band.tools.demo_app import clear_chaos

    recovery = clear_chaos()
    return {"merge": merge, "recovery": recovery, "ok": merge["ok"]}
