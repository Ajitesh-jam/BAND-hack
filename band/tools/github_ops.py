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

from band.config import get_settings, get_working_repo_url

# Files that must never be pushed to a public repo (contain Band credentials/logs).
_PUBLISH_EXCLUDE = {"agent_config.yaml", "agent.log", "band_integration.log", "__pycache__"}

WORKING_REPO_DIR = "repo"


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


def _working_repo_path() -> Path:
    return _workspace() / WORKING_REPO_DIR


def _local_demo_fallback() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "demo-app"


def _configured_repo_url() -> str:
    return get_working_repo_url()


def _repo_slug_from_url(url: str) -> str | None:
    text = url.rstrip("/")
    if "github.com/" not in text:
        return None
    return text.split("github.com/", 1)[-1].removesuffix(".git")


def _repo_slug() -> str | None:
    """e.g. owner/repo from configured working repo URL."""
    return _repo_slug_from_url(_configured_repo_url())


def _remote_origin_url(cwd: Path) -> str | None:
    result = _run(["git", "remote", "get-url", "origin"], cwd=cwd)
    if result["ok"] and result["stdout"].strip():
        return result["stdout"].strip()
    return None


def _urls_match(configured: str, remote: str | None) -> bool:
    if not configured or not remote:
        return False
    configured_slug = parse_github_repo_url(configured)
    remote_slug = parse_github_repo_url(remote)
    return bool(configured_slug and remote_slug and configured_slug == remote_slug)


def _authenticated_clone_url(repo_url: str) -> str:
    settings = get_settings()
    token = settings.demo_app_github_token
    if token and repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://{token}@")
    return repo_url


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
    candidates: list[Path] = []
    if cwd is not None:
        candidates.append(cwd)
    if _configured_repo_url():
        candidates.append(_working_repo_path())
    else:
        candidates.append(_local_demo_fallback())

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
    base = _repo_base()
    return {
        "ok": True,
        "repo": slug,
        "default_branch": branch,
        "workspace_path": str(base),
    }


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
    """Clone or update the shared working repo at .workspace/repo."""
    repo_url = _configured_repo_url()
    if not repo_url:
        local = _local_demo_fallback()
        return {"ok": True, "path": str(local), "mode": "local", "workspace_path": str(local)}

    target = _working_repo_path()
    clone_url = _authenticated_clone_url(repo_url)

    if target.exists():
        origin = _remote_origin_url(target)
        if not _urls_match(repo_url, origin):
            shutil.rmtree(target, ignore_errors=True)
        else:
            pull = _run(["git", "pull", "--rebase"], cwd=target)
            if pull["ok"]:
                return {
                    **pull,
                    "path": str(target),
                    "workspace_path": str(target),
                    "default_branch": default_branch(target),
                    "repo": _repo_slug(),
                    "mode": "pull",
                }
            shutil.rmtree(target, ignore_errors=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    clone = _run(["git", "clone", clone_url, str(target)])
    return {
        **clone,
        "path": str(target),
        "workspace_path": str(target),
        "default_branch": default_branch(target if target.exists() else None),
        "repo": _repo_slug(),
        "mode": "clone" if clone["ok"] else "clone_failed",
    }


def ensure_working_repo(repo_url: str | None = None) -> dict[str, Any]:
    """Ensure .workspace/repo exists and matches the configured (or given) GitHub URL."""
    if repo_url:
        slug = parse_github_repo_url(repo_url)
        if not slug:
            return {"ok": False, "error": f"invalid GitHub URL: {repo_url}"}
        target = _working_repo_path()
        if target.exists():
            origin = _remote_origin_url(target)
            if _urls_match(repo_url, origin):
                pull = _run(["git", "pull", "--rebase"], cwd=target)
                if pull["ok"]:
                    return {
                        "ok": True,
                        "path": str(target),
                        "workspace_path": str(target),
                        "repo": slug,
                        "mode": "pull",
                    }
            shutil.rmtree(target, ignore_errors=True)
        return clone_public_repo(repo_url, dest=target)
    return clone_or_pull_repo()


def create_branch(branch_name: str) -> dict[str, Any]:
    if not _configured_repo_url():
        local = _local_demo_fallback()
        return {"ok": True, "path": str(local), "branch": branch_name, "mode": "local"}
    target = _working_repo_path()
    checkout = _run(["git", "checkout", "-b", branch_name], cwd=target)
    return {**checkout, "path": str(target), "workspace_path": str(target), "branch": branch_name}


def _repo_base() -> Path:
    """Local path of the shared working clone (or bundled demo-app for local mode)."""
    if not _configured_repo_url():
        return _local_demo_fallback()
    return _working_repo_path()


def write_file(relative_path: str, content: str) -> dict[str, Any]:
    base = _repo_base()
    target = base / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"ok": True, "path": str(target)}


def read_file(relative_path: str) -> dict[str, Any]:
    """Read a file from the working clone so the coder edits real content, not guesses."""
    base = _repo_base()
    target = base / relative_path
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": f"file not found: {relative_path}", "relative_path": relative_path}
    try:
        return {"ok": True, "relative_path": relative_path, "content": target.read_text(encoding="utf-8")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "relative_path": relative_path}


def list_repo_files(subdir: str | None = None, limit: int = 200) -> dict[str, Any]:
    """List source files in the working clone so agents reference real paths."""
    base = _repo_base()
    root = base / subdir if subdir else base
    if not root.exists():
        return {"ok": False, "error": f"path not found: {subdir or '.'}"}
    skip = {".git", "__pycache__", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip for part in path.relative_to(base).parts):
            continue
        files.append(str(path.relative_to(base)))
        if len(files) >= limit:
            break
    return {"ok": True, "base": str(base), "count": len(files), "files": files}


def commit_and_push(message: str, branch: str) -> dict[str, Any]:
    settings = get_settings()
    if not _configured_repo_url():
        return {"ok": True, "mode": "local", "message": "skipped push in local mode"}
    target = _working_repo_path()
    _run(["git", "add", "-A"], cwd=target)
    commit = _run(["git", "commit", "-m", message], cwd=target)
    if not commit["ok"] and "nothing to commit" in commit["stdout"] + commit["stderr"]:
        return {"ok": False, "error": "nothing to commit"}
    # Without a token we cannot push. The change is committed locally and the reviewer
    # can still review the local diff — treat this as success so the flow doesn't stall.
    if not settings.demo_app_github_token:
        return {
            "ok": True,
            "mode": "local-commit",
            "commit": commit,
            "branch": branch,
            "message": (
                f"Committed to local branch '{branch}'. Push/PR skipped (no GITHUB_TOKEN); "
                "reviewer can review the local diff."
            ),
        }
    push = _run(["git", "push", "-u", "origin", branch], cwd=target)
    return {"commit": commit, "push": push, "ok": push["ok"]}


def open_pull_request(title: str, body: str, branch: str, base: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    if not _configured_repo_url():
        return {
            "ok": True,
            "mode": "local",
            "pr_url": f"https://github.com/example/bandaid-demo/pull/local-{branch}",
            "title": title,
        }
    target = _working_repo_path()
    env = _gh_env()
    resolved_base = base or default_branch()

    # Graceful degradation: without gh or a token we cannot open a real PR.
    # Return a terminal, non-error result so the workflow does not loop.
    slug = _repo_slug()
    if not settings.demo_app_github_token or not shutil.which("gh"):
        compare_url = (
            f"https://github.com/{slug}/compare/{resolved_base}...{branch}?expand=1"
            if slug
            else None
        )
        reason = (
            "GITHUB_TOKEN not set" if not settings.demo_app_github_token
            else "gh CLI not installed"
        )
        return {
            "ok": True,
            "mode": "manual",
            "pr_opened": False,
            "requires_token": True,
            "reason": reason,
            "compare_url": compare_url,
            "pr_url": compare_url,
            "branch": branch,
            "base": resolved_base,
            "message": (
                f"Could not open a PR automatically ({reason}). The fix is committed on "
                f"branch '{branch}'. Open the PR manually via the compare URL, or set "
                "GITHUB_TOKEN and install gh to automate it."
            ),
        }

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
    if not shutil.which("gh"):
        return {"ok": False, "error": "gh CLI not installed"}
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


def _local_branch_diff(target: Path) -> dict[str, Any] | None:
    """Diff the coder's committed work against the repo's default branch, locally.

    Works without gh or a token: the reviewer reads the same shared working clone
    that the coder edited, so it can review the real change before any PR exists.
    """
    if not (target / ".git").exists():
        return None
    base = default_branch(target)
    for ref in (f"origin/{base}", base):
        check = _run(["git", "rev-parse", "--verify", ref], cwd=target)
        if check["ok"]:
            diff = _run(["git", "diff", f"{ref}...HEAD"], cwd=target)
            if diff["ok"] and diff["stdout"].strip():
                return {"ok": True, "mode": "local-git", "base": base, "diff": diff["stdout"]}
    # Fall back to uncommitted / staged workspace changes (coder uses write_file without push).
    for args in (["git", "diff", "HEAD"], ["git", "diff"]):
        diff = _run(args, cwd=target)
        if diff["ok"] and diff["stdout"].strip():
            return {"ok": True, "mode": "local-working-tree", "base": base, "diff": diff["stdout"]}
    diff = _run(["git", "diff", "HEAD~1...HEAD"], cwd=target)
    if diff["ok"] and diff["stdout"].strip():
        return {"ok": True, "mode": "local-git", "base": base, "diff": diff["stdout"]}
    status = _run(["git", "show", "--stat", "HEAD"], cwd=target)
    if status["ok"] and status["stdout"].strip():
        return {"ok": True, "mode": "local-git", "base": base, "diff": status["stdout"]}
    return None


def fetch_pr_diff(pr_url_or_number: str) -> dict[str, Any]:
    settings = get_settings()
    pr_number = extract_pr_number(pr_url_or_number) or pr_url_or_number
    # Prefer a real local diff from the shared working clone (no gh/token needed).
    local = _local_branch_diff(_repo_base())
    if local:
        return {**local, "pr_number": pr_number}
    if not _configured_repo_url() or not shutil.which("gh"):
        return {
            "ok": False,
            "mode": "unavailable",
            "error": "no local diff available and gh CLI not installed; ask coder to post the changed files",
            "pr_number": pr_number,
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
    pr_number = extract_pr_number(pr_url_or_number) or pr_url_or_number
    if not _configured_repo_url():
        from band.tools.demo_app import clear_chaos

        clear_result = clear_chaos()
        return {"ok": True, "mode": "local", "merge": "simulated", "recovery": clear_result}
    env = _gh_env()
    merge = _run(_gh_pr_cmd("merge", pr_number, "--squash", "--delete-branch"), env=env)
    from band.tools.demo_app import clear_chaos

    recovery = clear_chaos()
    return {"merge": merge, "recovery": recovery, "ok": merge["ok"]}
