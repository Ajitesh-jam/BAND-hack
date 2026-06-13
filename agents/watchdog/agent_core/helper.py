import time
from datetime import UTC, datetime
from typing import Any

import httpx
from dotenv import load_dotenv
from band.client import BandAgentClient
from band.config import get_settings
from band.registry import load_agent_config
import logging

logger = logging.getLogger(__name__)

_incident_counter = 0
_active_incident: dict[str, Any] | None = None


def _next_incident_id() -> str:
    global _incident_counter
    _incident_counter += 1
    return f"INC-{datetime.now(UTC).strftime('%m%d')}-{_incident_counter:03d}"


def classify_failure(health: dict[str, Any]) -> str:
    """Human-readable failure reason for alerts."""
    if err := health.get("error"):
        if "timed out" in str(err).lower():
            return "probe_timeout"
        return "probe_error"
    body = health.get("body") or {}
    if fault := body.get("active_fault"):
        return str(fault)
    if body.get("status") == "unhealthy":
        return "unhealthy"
    return "unknown"


def check_health() -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.demo_app_url.rstrip('/')}{settings.watchdog_health_path}"
    attempts = max(1, settings.watchdog_health_retries + 1)
    last: dict[str, Any] = {"healthy": False, "error": "no attempts"}

    for attempt in range(attempts):
        try:
            response = httpx.get(url, timeout=settings.watchdog_health_timeout_s)
            body = (
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            healthy = response.status_code == 200 and body.get("status") == "healthy"
            result: dict[str, Any] = {
                "healthy": healthy,
                "status_code": response.status_code,
                "body": body,
            }
            if not healthy:
                result["failure_reason"] = classify_failure(result)
            return result
        except httpx.HTTPError as exc:
            last = {"healthy": False, "error": str(exc), "failure_reason": classify_failure({"error": str(exc)})}
            if attempt + 1 < attempts:
                time.sleep(1)
    return last


def _fetch_chaos_status() -> dict[str, Any] | None:
    settings = get_settings()
    url = f"{settings.demo_app_url.rstrip('/')}/chaos/status"
    try:
        response = httpx.get(url, timeout=3.0)
        return response.json() if response.is_success else None
    except httpx.HTTPError:
        return None


def _find_peer(peers: list[dict[str, Any]], handle_fragment: str) -> dict[str, Any] | None:
    fragment = handle_fragment.lower().replace("@", "")
    for peer in peers:
        for key in ("handle", "name", "username"):
            value = str(peer.get(key, "")).lower()
            if fragment in value:
                return peer
    return None


def _find_peer_id(peers: list[dict[str, Any]], handle_fragment: str) -> str | None:
    peer = _find_peer(peers, handle_fragment)
    if peer:
        return peer.get("id") or peer.get("participant_id")
    return None


def open_incident_room(client: BandAgentClient, health: dict[str, Any]) -> dict[str, Any]:
    global _active_incident
    settings = get_settings()
    incident_id = _next_incident_id()
    # task_id must reference an existing Band task; omit it and use incident_id in messages.
    room = client.create_chat()
    chat_id = room.get("id") or room.get("chat_id")
    if not chat_id:
        raise RuntimeError(f"Failed to create incident room: {room}")

    peers = client.list_peers(not_in_chat=chat_id)
    commander = _find_peer(peers, settings.commander_handle)
    if not commander:
        raise RuntimeError(
            f"Commander agent '{settings.commander_handle}' not found among peers. "
            "Run scripts/setup_agents.py and ensure all agents are registered."
        )
    client.add_participant(chat_id, commander["id"])

    failure_reason = health.get("failure_reason") or classify_failure(health)
    chaos_status = _fetch_chaos_status()
    active_fault = (health.get("body") or {}).get("active_fault")
    if not active_fault and chaos_status:
        active_fault = chaos_status.get("active_fault")

    alert = {
        "incident_id": incident_id,
        "severity": health.get("body", {}).get("severity", "critical"),
        "service": "checkout-api",
        "status": "open",
        "detected_at": datetime.now(UTC).isoformat(),
        "health": health,
        "fault": active_fault or failure_reason,
        "failure_reason": failure_reason,
        "chaos_status": chaos_status,
    }

    commander_name = commander.get("name") or settings.commander_handle
    mentions = [
        {
            "id": commander["id"],
            "handle": commander.get("handle"),
            "name": commander_name,
        }
    ]

    if failure_reason == "probe_timeout":
        summary = "Health probe timed out (no response within probe deadline)."
    elif active_fault:
        summary = f"Service unhealthy — chaos fault `{active_fault}`."
    else:
        summary = "Service unhealthy."

    content = (
        f"🚨 **{incident_id}** — Production alert\n\n"
        f"{summary}\n"
        f"Failure reason: `{alert.get('fault')}`\n"
        f"Severity: `{alert.get('severity')}`\n\n"
        f"```json\n{alert}\n```\n\n"
        f"@{commander_name} please classify and recruit specialists."
    )
    client.send_message(chat_id, content, mentions=mentions)
    client.send_event(
        chat_id,
        f"Incident {incident_id} opened by watchdog",
        "task",
        metadata={"incident_id": incident_id, "status": "open"},
    )

    _active_incident = {
        "incident_id": incident_id,
        "chat_id": chat_id,
        "alert": alert,
    }
    logger.info("Opened incident room %s (chat %s)", incident_id, chat_id)
    return _active_incident


def monitor_loop() -> None:
    global _active_incident
    load_dotenv()
    settings = get_settings()
    creds = load_agent_config("watchdog")

    logger.info("Watchdog monitoring %s", settings.demo_app_url)

    with BandAgentClient(creds.agent_id, creds.api_key) as client:
        me = client.me()
        logger.info("Connected as %s", me.get("name", me.get("handle", creds.agent_id)))

        was_healthy = True
        consecutive_failures = 0
        threshold = max(1, settings.watchdog_failure_threshold)

        while True:
            health = check_health()
            healthy = health.get("healthy", False)

            if healthy:
                consecutive_failures = 0
                if not was_healthy:
                    logger.info("Service recovered")
                    if _active_incident:
                        chat_id = _active_incident["chat_id"]
                        client.send_event(
                            chat_id,
                            f"Service health restored for {_active_incident['incident_id']}",
                            "task",
                            metadata={"status": "resolved"},
                        )
                        _active_incident = None
            else:
                consecutive_failures += 1
                reason = health.get("failure_reason") or classify_failure(health)
                if consecutive_failures < threshold:
                    logger.warning(
                        "Health check failed (%s) — %s/%s before opening incident",
                        reason,
                        consecutive_failures,
                        threshold,
                    )
                elif not _active_incident:
                    logger.warning(
                        "Service unhealthy (%s) — opening incident room",
                        reason,
                    )
                    try:
                        open_incident_room(client, health)
                    except Exception:
                        logger.exception("Failed to open incident room")

            was_healthy = healthy
            time.sleep(settings.watchdog_poll_interval_s)
