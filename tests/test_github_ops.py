"""Tests for GitHub helper utilities."""

from __future__ import annotations

from pathlib import Path

from band.tools import github_ops
from band.tools.github_ops import (
    _pr_url_from_gh_output,
    _repo_slug,
    _run,
    default_branch,
    extract_pr_number,
    parse_github_repo_url,
)


def test_extract_pr_number_from_url():
    assert extract_pr_number("https://github.com/org/repo/pull/42") == "42"


def test_extract_pr_number_from_hash():
    assert extract_pr_number("PR #17 ready for review") == "17"


def test_repo_slug_from_https_url(monkeypatch):
    monkeypatch.setenv("DEMO_APP_REPO", "https://github.com/kalki-kgp/bandaid-demo-app.git")
    from band.config import get_settings

    get_settings.cache_clear()
    assert _repo_slug() == "kalki-kgp/bandaid-demo-app"
    get_settings.cache_clear()


def test_pr_url_from_gh_already_exists_stderr():
    stderr = (
        'a pull request for branch "fix/foo" already exists:\n'
        "https://github.com/org/repo/pull/1\n"
    )
    assert _pr_url_from_gh_output("", stderr) == "https://github.com/org/repo/pull/1"


def test_parse_github_repo_url_variants():
    assert parse_github_repo_url("https://github.com/org/repo") == "org/repo"
    assert parse_github_repo_url("https://github.com/org/repo.git") == "org/repo"
    assert parse_github_repo_url("org/repo") == "org/repo"
    assert parse_github_repo_url("not-a-url") is None


def test_run_missing_command_returns_error():
    result = _run(["definitely-not-a-real-binary-xyz"])
    assert result["ok"] is False
    assert result["returncode"] == 127
    assert "not found" in result["stderr"]


def test_default_branch_without_gh_uses_git(tmp_path, monkeypatch):
    repo = tmp_path / "demo-app"
    repo.mkdir()
    monkeypatch.setattr(github_ops, "_workspace", lambda: tmp_path)
    monkeypatch.setenv("DEMO_APP_REPO", "https://github.com/org/demo-app.git")
    from band.config import get_settings

    get_settings.cache_clear()

    init = _run(["git", "init", "-b", "develop"], cwd=repo)
    assert init["ok"]
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("hi", encoding="utf-8")
    _run(["git", "add", "README.md"], cwd=repo)
    _run(["git", "commit", "-m", "init"], cwd=repo)
    _run(["git", "remote", "add", "origin", "https://github.com/org/demo-app.git"], cwd=repo)
    _run(["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop"], cwd=repo)

    monkeypatch.setattr(github_ops.shutil, "which", lambda name: None)
    assert default_branch(repo) == "develop"
    get_settings.cache_clear()
