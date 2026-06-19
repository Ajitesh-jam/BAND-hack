"""Tools for interacting with the demo checkout API."""

from __future__ import annotations

import json
from typing import Any

import httpx

from band.config import get_settings


def _base_url() -> str:
    settings = get_settings()
    return (settings.hosted_app_url or settings.demo_app_url).rstrip("/")


def fetch_health() -> dict[str, Any]:
    """Return demo-app health status."""
    url = f"{_base_url()}/health"
    try:
        response = httpx.get(url, timeout=10.0)
        return {"status_code": response.status_code, "body": response.json(), "url": url}
    except httpx.ConnectError as exc:
        return {
            "status_code": 0,
            "body": {"status": "unreachable", "error": str(exc)},
            "url": url,
            "failure_reason": "probe_error",
        }


def fetch_metrics() -> dict[str, Any]:
    """Return Prometheus-style metrics from demo-app."""
    response = httpx.get(f"{_base_url()}/metrics", timeout=10.0)
    return {"status_code": response.status_code, "body": response.text}


def fetch_logs(limit: int = 100, level: str | None = None) -> dict[str, Any]:
    """Fetch recent structured logs from demo-app."""
    params: dict[str, Any] = {"limit": limit}
    if level:
        params["level"] = level
    response = httpx.get(f"{_base_url()}/logs", params=params, timeout=15.0)
    return {"status_code": response.status_code, "body": response.json()}


def fetch_chaos_status() -> dict[str, Any]:
    """Return active chaos/fault injection state."""
    response = httpx.get(f"{_base_url()}/chaos/status", timeout=10.0)
    return {"status_code": response.status_code, "body": response.json()}


def trigger_chaos(fault: str) -> dict[str, Any]:
    """Inject a fault: pool_exhaustion, pii_leak, or bad_config."""
    response = httpx.post(
        f"{_base_url()}/chaos/{fault}",
        timeout=10.0,
    )
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = response.text
    return {"status_code": response.status_code, "body": body}


def clear_chaos() -> dict[str, Any]:
    """Clear all active fault injections."""
    url = f"{_base_url()}/chaos/clear"
    try:
        response = httpx.post(url, timeout=10.0)
        return {"status_code": response.status_code, "body": response.json(), "url": url}
    except httpx.ConnectError as exc:
        return {
            "status_code": 0,
            "body": {"error": str(exc), "cleared": False},
            "url": url,
            "failure_reason": "probe_error",
            "hint": "Demo app is not running — start it on the health URL before restore_service.",
        }


def restart_service() -> dict[str, Any]:
    """Signal demo-app to reset internal state (simulated redeploy)."""
    response = httpx.post(f"{_base_url()}/chaos/clear", timeout=10.0)
    return {"status_code": response.status_code, "body": response.json(), "action": "redeploy_simulated"}
