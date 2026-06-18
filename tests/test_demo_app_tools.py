"""Tests for demo-app tool wrappers."""

from __future__ import annotations

from band.tools import demo_app


def test_is_healthy_body_ok():
    assert demo_app.is_healthy_body({"status": "ok", "systemHealth": {"status": "healthy"}})


def test_is_healthy_body_error():
    assert not demo_app.is_healthy_body({"status": "error", "crash": {"active": True}})


def test_is_healthy_body_legacy():
    assert demo_app.is_healthy_body({"status": "healthy"})
    assert not demo_app.is_healthy_body({"status": "healthy", "active_fault": "pool_exhaustion"})


def test_classify_health_body_crash():
    assert demo_app.classify_health_body({"crash": {"errorCode": "FATAL_APP_CRASH"}}) == "FATAL_APP_CRASH"
