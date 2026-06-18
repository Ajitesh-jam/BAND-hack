"""Tools for interacting with the hosted Band of Agents demo app (GitHub Pages)."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from band.config import get_health_path, get_hosted_app_url, get_settings


def _base_url() -> str:
    return get_hosted_app_url()


def _api_url(path: str) -> str:
    base = _base_url()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _repo_slug() -> str | None:
    url = (get_settings().demo_app_repo or "").rstrip("/")
    if "github.com/" not in url:
        return None
    return url.split("github.com/", 1)[-1].removesuffix(".git")


def is_healthy_body(body: dict[str, Any]) -> bool:
    """Return True when the demo app health payload indicates a healthy service."""
    if not body:
        return False
    status = str(body.get("status", "")).lower()
    if status in ("error", "unhealthy", "down", "crashed"):
        return False
    if body.get("errors"):
        return False
    if body.get("failure_reason"):
        return False
    if body.get("crash", {}).get("active"):
        return False
    system = body.get("systemHealth") or {}
    system_status = str(system.get("status", "")).lower()
    if system_status in ("error", "unhealthy", "down", "crashed"):
        return False
    if status == "ok":
        return True
    # Legacy FastAPI demo-app format
    if status == "healthy":
        return body.get("active_fault") is None
    return False


def classify_health_body(body: dict[str, Any]) -> str:
    if body.get("crash", {}).get("errorCode"):
        return str(body["crash"].get("errorCode", "FATAL_APP_CRASH"))
    if body.get("active_fault"):
        return str(body["active_fault"])
    system = body.get("systemHealth") or {}
    if system.get("status") == "error":
        return "system_error"
    status = str(body.get("status", "")).lower()
    if status in ("error", "unhealthy", "down", "crashed"):
        return status
    raw = str(body.get("raw", ""))
    if "DEPLOYMENT_NOT_FOUND" in raw:
        return "deployment_not_found"
    if raw:
        return "invalid_health_response"
    return "unknown"


def classify_health_response(status_code: int, body: dict[str, Any]) -> str:
    if status_code == 404:
        raw = str(body.get("raw", ""))
        if "DEPLOYMENT_NOT_FOUND" in raw:
            return "deployment_not_found"
        return "health_endpoint_not_found"
    if status_code >= 500:
        return "server_error"
    if status_code != 200:
        return f"http_{status_code}"
    return classify_health_body(body)


def fetch_health() -> dict[str, Any]:
    """Fetch hosted demo app health (GitHub Pages: /api/health.json)."""
    settings = get_settings()
    path = get_health_path(settings)
    url = _api_url(path)
    response = httpx.get(url, timeout=settings.watchdog_health_timeout_s, follow_redirects=True)
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"raw": response.text[:500]}
    healthy = response.status_code == 200 and is_healthy_body(body)
    if response.status_code == 503:
        healthy = False
    result: dict[str, Any] = {
        "healthy": healthy,
        "status_code": response.status_code,
        "body": body,
        "url": url,
    }
    if not healthy:
        result["failure_reason"] = classify_health_response(response.status_code, body)
    return result


def fetch_logs(limit: int = 100, level: str | None = None) -> dict[str, Any]:
    """Fetch activity logs from /api/logs.json."""
    url = _api_url("/api/logs.json")
    response = httpx.get(url, timeout=15.0, follow_redirects=True)
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"raw": response.text[:2000]}
    logs = body.get("logs") or []
    if level:
        level_l = level.lower()
        logs = [entry for entry in logs if str(entry.get("level", "")).lower() == level_l]
    if limit:
        logs = logs[:limit]
    return {
        "status_code": response.status_code,
        "url": url,
        "count": len(logs),
        "logs": logs,
        "body": body,
    }


def fetch_deployment_logs(limit: int = 50) -> dict[str, Any]:
    """Fetch build/deploy logs from /api/deployment-logs.json."""
    url = _api_url("/api/deployment-logs.json")
    response = httpx.get(url, timeout=15.0, follow_redirects=True)
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"raw": response.text[:2000]}
    logs = (body.get("logs") or [])[:limit]
    return {
        "status_code": response.status_code,
        "url": url,
        "count": len(logs),
        "logs": logs,
        "body": body,
    }


def fetch_inject_error_info() -> dict[str, Any]:
    """Return inject/recover API documentation from /api/inject-error.json."""
    url = _api_url("/api/inject-error.json")
    response = httpx.get(url, timeout=10.0, follow_redirects=True)
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"raw": response.text[:2000]}
    return {"status_code": response.status_code, "url": url, "body": body}


def fetch_chaos_status() -> dict[str, Any]:
    """Legacy FastAPI demo-app chaos status (if still running locally).

    Hosted GitHub Pages / Vercel deployments do not expose this route; callers
    should treat non-200 or empty bodies as "no legacy chaos state".
    """
    url = _api_url("/chaos/status")
    try:
        response = httpx.get(url, timeout=3.0, follow_redirects=True)
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {}
        return {"status_code": response.status_code, "url": url, "body": body}
    except httpx.HTTPError as exc:
        return {"status_code": 0, "error": str(exc), "url": url, "body": {}}


def _github_headers() -> dict[str, str] | None:
    token = get_settings().demo_app_github_token
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_update_health_json(*, crashed: bool) -> dict[str, Any]:
    """Patch api/health.json on gh-pages so watchdog/curl can see crash/recover."""
    slug = _repo_slug()
    headers = _github_headers()
    if not slug or not headers:
        return {
            "ok": False,
            "error": "GITHUB_TOKEN and DEMO_APP_REPO required for remote health patch",
        }

    path = "api/health.json"
    branch = "gh-pages"
    api = f"https://api.github.com/repos/{slug}/contents/{path}"

    with httpx.Client(timeout=20.0) as client:
        existing = client.get(api, params={"ref": branch}, headers=headers)
        sha = None
        if existing.status_code == 200:
            sha = existing.json().get("sha")

        if crashed:
            from datetime import UTC, datetime

            payload = {
                "status": "error",
                "timestamp": datetime.now(UTC).isoformat(),
                "systemHealth": {
                    "status": "error",
                    "agents": {"healthy": 0, "degraded": 0, "error": 5},
                    "metrics": {"avgCpu": 100, "avgMemory": 100, "avgResponseTime": 9999},
                },
                "crash": {
                    "active": True,
                    "errorCode": "FATAL_APP_CRASH",
                    "reason": "Injected via band recover/trigger API (health.json patched on gh-pages)",
                },
                "agents": [],
            }
        else:
            payload = {
                "status": "ok",
                "timestamp": "",
                "systemHealth": {
                    "status": "healthy",
                    "agents": {"healthy": 5, "degraded": 0, "error": 0},
                    "metrics": {"avgCpu": 12.0, "avgMemory": 18.0, "avgResponseTime": 80.0},
                },
                "agents": [
                    {"id": f"agent-{i}", "name": name, "status": "healthy"}
                    for i, name in enumerate(["Atlas", "Echo", "Nova", "Flux", "Iris"], start=1)
                ],
            }
            from datetime import UTC, datetime

            payload["timestamp"] = datetime.now(UTC).isoformat()

        content = base64.b64encode(json.dumps(payload, indent=2).encode()).decode()
        body: dict[str, Any] = {
            "message": "Recover demo app health" if not crashed else "Inject demo app fatal error",
            "content": content,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        put = client.put(api, headers=headers, json=body)

    return {
        "ok": put.is_success,
        "status_code": put.status_code,
        "body": put.json() if put.content else {},
        "crashed": crashed,
    }


def trigger_fatal_crash() -> dict[str, Any]:
    """Inject a server-detectable fatal error (local API + gh-pages health.json patch)."""
    patch = _github_update_health_json(crashed=True)
    local = httpx.post(
        _api_url("/api/crash"),
        json={"reason": "Injected by Band agent", "errorCode": "FATAL_APP_CRASH"},
        timeout=10.0,
        follow_redirects=True,
    )
    page = httpx.get(_api_url("/api/inject-error.html"), timeout=10.0, follow_redirects=True)
    return {
        "action": "inject_fatal_crash",
        "health_patch": patch,
        "local_crash_status": local.status_code,
        "inject_page_status": page.status_code,
        "health_after": fetch_health(),
    }


def recover_service() -> dict[str, Any]:
    """Recover the hosted demo app after a fatal crash."""
    patch = _github_update_health_json(crashed=False)
    local = httpx.delete(_api_url("/api/crash"), timeout=10.0, follow_redirects=True)
    recover_page = httpx.get(_api_url("/api/recover.html"), timeout=10.0, follow_redirects=True)
    recover_query = httpx.get(
        _api_url("/"),
        params={"recover": "true"},
        timeout=10.0,
        follow_redirects=True,
    )
    health = fetch_health()
    return {
        "action": "recover_service",
        "health_patch": patch,
        "local_recover_status": local.status_code,
        "recover_page_status": recover_page.status_code,
        "recover_query_status": recover_query.status_code,
        "health_after": health,
        "recovered": health.get("healthy", False),
    }


def clear_chaos() -> dict[str, Any]:
    """Clear legacy chaos faults or recover the GitHub Pages demo app."""
    chaos = fetch_chaos_status()
    if chaos.get("status_code") == 200 and chaos.get("body"):
        response = httpx.post(_api_url("/chaos/clear"), timeout=10.0, follow_redirects=True)
        try:
            body = response.json() if response.content else {}
        except json.JSONDecodeError:
            body = {"raw": response.text[:500]}
        return {
            "mode": "legacy_chaos_clear",
            "status_code": response.status_code,
            "body": body,
        }
    return recover_service()


def trigger_chaos(fault: str) -> dict[str, Any]:
    """Legacy FastAPI fault injection, or fatal crash for GitHub Pages demo."""
    url = _api_url(f"/chaos/{fault}")
    try:
        response = httpx.post(url, timeout=10.0, follow_redirects=True)
        if response.status_code == 404:
            return trigger_fatal_crash()
        try:
            body = response.json() if response.content else {}
        except json.JSONDecodeError:
            body = {"raw": response.text[:500]}
        return {"status_code": response.status_code, "body": body}
    except httpx.HTTPError:
        return trigger_fatal_crash()


def fetch_metrics() -> dict[str, Any]:
    """Legacy Prometheus metrics endpoint."""
    response = httpx.get(_api_url("/metrics"), timeout=10.0)
    return {"status_code": response.status_code, "body": response.text}


def restart_service() -> dict[str, Any]:
    return recover_service()
