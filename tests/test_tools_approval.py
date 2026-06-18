"""Tests for band.tools.approval toast UI."""

from __future__ import annotations

from band.tools import approval


def test_render_approval_is_compact_toast():
    html_bytes = approval._render_approval(
        "tok123",
        {"incident_id": "INC-001", "summary": "Branch fix-carousel\nFiles: app/page.tsx"},
    )
    text = html_bytes.decode()
    assert "toast" in text
    assert "Approve &amp; merge" in text
    assert "slideUp" in text
    assert "100vh" not in text  # not a full-page centered modal


def test_open_approval_toast_prefers_chrome(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(approval.os.path, "isfile", lambda p: "Chrome" in p)
    monkeypatch.setattr(approval.subprocess, "run", fake_run)
    mode = approval._open_approval_toast("http://127.0.0.1:8770/a/abc")
    assert mode == "chrome_app"
    assert any("--app=" in arg for cmd in calls for arg in cmd)
