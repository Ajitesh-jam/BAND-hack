"""Tests for GitHub helper utilities."""

from __future__ import annotations

from band.tools.github_ops import _pr_url_from_gh_output, _repo_slug, extract_pr_number


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
