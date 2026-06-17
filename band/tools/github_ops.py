"""Git and GitHub operations for fix engineer and reviewer."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from band.config import get_settings

# Files that must never be pushed to a public repo (contain Band credentials/logs).
_PUBLISH_EXCLUDE = {"agent_config.yaml", "agent.log", "band_integration.log", "__pycache__"}


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    merged_env = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=merged_env,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return {
            "returncode": 127,
            "stdout": "",
            "stderr": f"command not found: {cmd[0]}",
            "ok": False,
        }
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
    """Read default branch from local clone (origin HEAD or current branch)."""
    remote = _run(["git", "remote", "show", "origin"], cwd=cwd)
    if remote["ok"]:
        for line in remote["stdout"].splitlines():
            line = line.strip()
            if line.startswith("HEAD branch:"):
                return line.split(":", 1)[1].strip()

    head = _run(["git", "symbolic-ref", "--short", "HEAD"], cwd=cwd)
    if head["ok"] and head["stdout"].strip():
        return head["stdout"].strip()

    branch = _run(["git", "branch", "--show-current"], cwd=cwd)
    if branch["ok"] and branch["stdout"].strip():
        return branch["stdout"].strip()

    return None


def default_branch(cwd: Path | None = None) -> str:
    """Resolve the repo default branch — never guess main vs master."""
    settings = get_settings()
    candidates: list[Path] = []
    if cwd is not None:
        candidates.append(cwd)
    if settings.demo_app_repo:
        candidates.append(_workspace() / "demo-app")
    else:
        candidates.append(Path(__file__).resolve().parent.parent.parent / "demo-app")

    for target in candidates:
        if target.exists():
            branch = _default_branch_from_git(target)
            if branch:
                return branch

    repo = _repo_slug()
    if repo and shutil.which("gh"):
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
            env=_gh_env(),
        )
        if result["ok"] and result["stdout"].strip():
            return result["stdout"].strip()

    return "main"


def get_repo_info() -> dict[str, Any]:
    """Return repo slug and detected default branch for agents before git/gh commands."""
    slug = _repo_slug()
    branch = default_branch()
    return {"ok": True, "repo": slug, "default_branch": branch}


def parse_github_repo_url(url: str) -> str | None:
    """Normalize a GitHub URL to owner/repo slug."""
    text = url.strip().rstrip("/")
    if not text:
        return None
    if "github.com/" in text:
        slug = text.split("github.com/", 1)[-1]
    elif re.match(r"^[\w.-]+/[\w.-]+$", text):
        slug = text
    else:
        return None
    slug = slug.removesuffix(".git")
    parts = [p for p in slug.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def clone_public_repo(repo_url: str, dest: Path | None = None) -> dict[str, Any]:
    """Shallow-clone a public (or token-authenticated) GitHub repo into workspace."""
    slug = parse_github_repo_url(repo_url)
    if not slug:
        return {"ok": False, "error": f"invalid GitHub URL: {repo_url}"}

    safe_name = slug.replace("/", "-")
    target = dest or (_workspace() / f"company-context-{safe_name}")
    if target.exists():
        pull = _run(["git", "pull", "--rebase"], cwd=target)
        if pull["ok"]:
            return {"ok": True, "path": str(target), "repo": slug, "mode": "pull"}
        shutil.rmtree(target, ignore_errors=True)

    clone_url = f"https://github.com/{slug}.git"
    token = get_settings().demo_app_github_token
    if token:
        clone_url = f"https://{token}@github.com/{slug}.git"

    target.parent.mkdir(parents=True, exist_ok=True)
    clone = _run(["git", "clone", "--depth", "1", clone_url, str(target)])
    if not clone["ok"]:
        return {"ok": False, "error": clone["stderr"].strip() or "git clone failed", "repo": slug}
    return {"ok": True, "path": str(target), "repo": slug, "mode": "clone"}


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
        return {
            **pull,
            "path": str(target),
            "default_branch": default_branch(target),
            "repo": _repo_slug(),
        }

    clone = _run(["git", "clone", repo_url, str(target)])
    return {
        **clone,
        "path": str(target),
        "default_branch": default_branch(target if target.exists() else None),
        "repo": _repo_slug(),
    }


def create_branch(branch_name: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.demo_app_repo:
        local = Path(__file__).resolve().parent.parent.parent / "demo-app"
        return {"ok": True, "path": str(local), "branch": branch_name, "mode": "local"}
    target = _workspace() / "demo-app"
    checkout = _run(["git", "checkout", "-b", branch_name], cwd=target)
    return {**checkout, "path": str(target), "branch": branch_name}


def _repo_base() -> Path:
    settings = get_settings()
    if not settings.demo_app_repo:
        return Path(__file__).resolve().parent.parent.parent / "demo-app"
    return _workspace() / "demo-app"


def read_file(relative_path: str) -> dict[str, Any]:
    """Read a file from the working clone or local demo-app."""
    target = _repo_base() / relative_path.lstrip("/")
    if not target.exists():
        return {"ok": False, "error": f"file not found: {relative_path}"}
    try:
        content = target.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": str(target), "content": content}


def get_branch_diff(branch: str, base: str | None = None) -> dict[str, Any]:
    """Return git diff base...branch in the working clone."""
    settings = get_settings()
    if not settings.demo_app_repo:
        local = _repo_base()
        resolved_base = base or default_branch(local)
        diff = _run(["git", "diff", f"{resolved_base}...{branch}"], cwd=local)
        if not diff["ok"] and diff.get("stderr"):
            diff = _run(["git", "diff", resolved_base, branch], cwd=local)
        return {**diff, "branch": branch, "base": resolved_base, "mode": "local"}

    target = _workspace() / "demo-app"
    resolved_base = base or default_branch(target)
    diff = _run(["git", "diff", f"{resolved_base}...{branch}"], cwd=target)
    if not diff["ok"]:
        diff = _run(["git", "diff", resolved_base, branch], cwd=target)
    return {**diff, "branch": branch, "base": resolved_base, "diff": diff.get("stdout", "")}


def write_file(relative_path: str, content: str) -> dict[str, Any]:
    base = _repo_base()
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


def _agents_repo_slug() -> str | None:
    """Slug for the repo that hosts generated agents (AGENTS_REPO or demo repo)."""
    settings = get_settings()
    url = (settings.agents_repo or settings.demo_app_repo).rstrip("/")
    if "github.com/" not in url:
        return None
    return url.split("github.com/", 1)[-1].removesuffix(".git")


def publish_agent_pr(
    folder_path: str,
    title: str | None = None,
    body: str | None = None,
    dest_subdir: str = "generated_agents",
    base: str | None = None,
) -> dict[str, Any]:
    """Open a GitHub PR that adds a generated agent's code to the agents repo.

    Clones the target repo, copies the agent folder (excluding credentials and
    logs) into ``<dest_subdir>/<agent_name>/`` on a fresh branch, commits,
    pushes, and opens a pull request.

    Returns dict with ok/pr_url/branch or an error.
    """
    src = Path(folder_path).expanduser().resolve()
    if not src.exists() or not src.is_dir():
        return {"ok": False, "error": f"agent folder not found: {folder_path}"}

    repo_slug = _agents_repo_slug()
    settings = get_settings()
    token = settings.demo_app_github_token
    if not repo_slug:
        return {
            "ok": False,
            "error": "No agents repo configured. Set AGENTS_REPO (or DEMO_APP_REPO) to a github.com URL.",
        }
    if not token:
        return {"ok": False, "error": "No GITHUB_TOKEN configured — cannot push or open a PR."}

    agent_name = src.name
    branch = f"add-agent-{agent_name}-{uuid.uuid4().hex[:6]}"
    clone_url = f"https://{token}@github.com/{repo_slug}.git"

    work = _workspace() / f"agents-repo-{uuid.uuid4().hex[:6]}"
    clone = _run(["git", "clone", "--depth", "1", clone_url, str(work)])
    if not clone["ok"]:
        return {"ok": False, "error": f"git clone failed: {clone['stderr'].strip()}", "step": "clone"}

    try:
        resolved_base = base or (_default_branch_from_git(work) or "main")
        checkout = _run(["git", "checkout", "-b", branch], cwd=work)
        if not checkout["ok"]:
            return {"ok": False, "error": checkout["stderr"].strip(), "step": "checkout"}

        dest = work / dest_subdir / agent_name
        _copy_agent_tree(src, dest)

        _run(["git", "add", "-A"], cwd=work)
        commit = _run(
            ["git", "commit", "-m", title or f"Add generated Band agent: {agent_name}"],
            cwd=work,
        )
        if not commit["ok"] and "nothing to commit" in commit["stdout"] + commit["stderr"]:
            return {"ok": False, "error": "nothing to commit (agent files already present?)", "step": "commit"}

        push = _run(["git", "push", "-u", "origin", branch], cwd=work)
        if not push["ok"]:
            return {"ok": False, "error": push["stderr"].strip(), "step": "push"}

        pr_body = body or (
            f"Adds the generated Band agent `{agent_name}` under `{dest_subdir}/`.\n\n"
            "Credentials (agent_config.yaml) and logs are intentionally excluded."
        )
        cmd = [
            "gh", "pr", "create", "--repo", repo_slug,
            "--title", title or f"Add generated Band agent: {agent_name}",
            "--body", pr_body,
            "--head", branch,
            "--base", resolved_base,
        ]
        result = _run(cmd, cwd=work, env=_gh_env())
        pr_url = result["stdout"].strip() if result["ok"] else None
        if not pr_url:
            pr_url = _pr_url_from_gh_output(result["stdout"], result["stderr"])
        if not pr_url:
            return {
                "ok": False,
                "error": result["stderr"].strip() or "gh pr create failed",
                "step": "pr",
                "branch": branch,
            }
        return {"ok": True, "pr_url": pr_url, "branch": branch, "repo": repo_slug, "base": resolved_base}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _copy_agent_tree(src: Path, dest: Path) -> None:
    """Copy the agent folder to dest, skipping credentials, logs, and caches."""
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(*_PUBLISH_EXCLUDE, "*.pyc"),
    )
    # Leave a redacted example so the PR documents required credentials.
    (dest / "agent_config.yaml.example").write_text(
        "agent:\n  name: <agent-name>\n  agent_id: <band-agent-uuid>\n  api_key: <band-api-key>\n",
        encoding="utf-8",
    )


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
