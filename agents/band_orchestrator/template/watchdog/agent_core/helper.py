"""Hosted-app health monitoring and incident-room creation."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from dotenv import load_dotenv

from band.client import BandAgentClient
from band.config import get_settings
from band.registry import load_agent_config

logger = logging.getLogger(__name__)

_incident_counter = 0
_active_incident: dict[str, Any] | None = None


def clear_watchdog_context(reason: str = "manual") -> None:
    """Drop in-memory incident tracking so the next failure starts fresh."""
    global _active_incident
    if _active_incident:
        logger.info(
            "Watchdog context cleared (%s); was tracking %s",
            reason,
            _active_incident.get("incident_id"),
        )
    else:
        logger.info("Watchdog context cleared (%s)", reason)
    _active_incident = None


def get_active_incident() -> dict[str, Any] | None:
    return _active_incident


def _incident_room_exists(client: BandAgentClient, chat_id: str) -> bool:
    """Return False when the incident room was deleted on Band."""
    try:
        client.get_chat_context(chat_id)
        return True
    except Exception:  # noqa: BLE001
        return False


def _maybe_refresh_context(
    client: BandAgentClient,
    *,
    last_refresh_at: float,
    refresh_interval_s: float,
) -> tuple[float, bool, bool]:
    """Clear stale context when the room is gone or on a periodic timer."""
    cleared = False
    reset_failures = False
    now = time.monotonic()

    if _active_incident:
        chat_id = str(_active_incident.get("chat_id") or "")
        if chat_id and not _incident_room_exists(client, chat_id):
            clear_watchdog_context("room_deleted")
            cleared = True
            reset_failures = True

    if refresh_interval_s > 0 and (now - last_refresh_at) >= refresh_interval_s:
        if _active_incident:
            clear_watchdog_context("scheduled_refresh")
        else:
            logger.info("Watchdog scheduled context refresh")
        cleared = True
        reset_failures = True
        last_refresh_at = now

    return last_refresh_at, cleared, reset_failures


def _next_incident_id() -> str:
    global _incident_counter
    _incident_counter += 1
    return f"INC-{datetime.now(UTC).strftime('%m%d')}-{_incident_counter:03d}"


def classify_failure(health: dict[str, Any]) -> str:
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
    base = settings.hosted_app_url or settings.demo_app_url
    url = f"{base.rstrip('/')}{settings.watchdog_health_path}"
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
                "url": url,
            }
            if not healthy:
                result["failure_reason"] = classify_failure(result)
            return result
        except httpx.HTTPError as exc:
            last = {
                "healthy": False,
                "error": str(exc),
                "url": url,
                "failure_reason": classify_failure({"error": str(exc)}),
            }
            if attempt + 1 < attempts:
                time.sleep(1)
    return last


def _fetch_chaos_status() -> dict[str, Any] | None:
    settings = get_settings()
    base = settings.hosted_app_url or settings.demo_app_url
    url = f"{base.rstrip('/')}/chaos/status"
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
            if fragment and fragment in value:
                return peer
    return None


def _find_peer_id(peers: list[dict[str, Any]], handle_fragment: str) -> str | None:
    peer = _find_peer(peers, handle_fragment)
    if not peer:
        return None
    return peer.get("id") or peer.get("participant_id")


def _add_peer(
    client: BandAgentClient,
    chat_id: str,
    peers: list[dict[str, Any]],
    handle_fragment: str | list[str],
) -> dict[str, Any] | None:
    fragments = [handle_fragment] if isinstance(handle_fragment, str) else handle_fragment
    peer = None
    for fragment in fragments:
        peer = _find_peer(peers, fragment)
        if peer:
            break
    if not peer:
        logger.warning("Peer %s not found for incident room", fragments)
        return None
    peer_id = peer.get("id") or peer.get("participant_id")
    if not peer_id:
        logger.warning("Peer %s has no id: %s", handle_fragment, peer)
        return None
    client.add_participant(chat_id, peer_id)
    return peer


def _find_human(peers: list[dict[str, Any]]) -> dict[str, Any] | None:
    for peer in peers:
        if str(peer.get("type", "")).lower() == "user":
            return peer
    return None


def _add_human(
    client: BandAgentClient, chat_id: str, peers: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Add the account owner (a Band User, not an Agent) so they can post approvals."""
    human = _find_human(peers)
    if not human:
        return None
    human_id = human.get("id") or human.get("participant_id")
    if not human_id:
        return None
    try:
        client.add_participant(chat_id, human_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not add human %s to incident room: %s", human_id, exc)
        return None
    return human


def open_incident_room(client: BandAgentClient, health: dict[str, Any]) -> dict[str, Any]:
    global _active_incident
    settings = get_settings()
    incident_id = _next_incident_id()
    room = client.create_chat()
    chat_id = room.get("id") or room.get("chat_id")
    if not chat_id:
        raise RuntimeError(f"Failed to create incident room: {room}")

    peers = client.list_peers(not_in_chat=chat_id)
    # Bring the WHOLE roster in up front so no agent is "not found" mid-handoff
    # (the planner used to fail to hand off to the coder because coder/reviewer
    # were never added to the room).
    invited = [
        _add_peer(client, chat_id, peers, [settings.commander_handle, "incident-commander"]),
        _add_peer(client, chat_id, peers, [settings.planner_handle, "log-analyst"]),
        _add_peer(client, chat_id, peers, [settings.documentation_handle, "scribe"]),
        _add_peer(client, chat_id, peers, [settings.coder_handle, "fix-engineer"]),
        _add_peer(client, chat_id, peers, [settings.reviewer_handle, "reviewer"]),
    ]
    invited = [peer for peer in invited if peer]
    if not invited:
        raise RuntimeError("No company agents found among peers. Run setup and start agents first.")

    # Add the human owner so they can approve directly in the incident room.
    human = _add_human(client, chat_id, peers)
    if human is None:
        logger.warning("No human (type=User) peer found; approval must happen via notification")

    failure_reason = health.get("failure_reason") or classify_failure(health)
    chaos_status = _fetch_chaos_status()
    active_fault = (health.get("body") or {}).get("active_fault")
    if not active_fault and chaos_status:
        active_fault = chaos_status.get("active_fault")

    alert = {
        "incident_id": incident_id,
        "severity": health.get("body", {}).get("severity", "critical"),
        "service": "hosted-app",
        "status": "open",
        "detected_at": datetime.now(UTC).isoformat(),
        "health": health,
        "fault": active_fault or failure_reason,
        "failure_reason": failure_reason,
        "chaos_status": chaos_status,
    }

    commander_peer = invited[0]
    commander_name = (
        commander_peer.get("name")
        or commander_peer.get("handle")
        or commander_peer.get("username")
        or settings.commander_handle
    )
    mentions = [
        {
            "id": commander_peer.get("id") or commander_peer.get("participant_id"),
            "handle": commander_peer.get("handle"),
            "name": commander_name,
        }
    ]
    content = (
        f"ALERT {incident_id} - hosted app health failed\n\n"
        f"Failure reason: `{alert['fault']}`\n"
        f"Severity: `{alert['severity']}`\n\n"
        f"```json\n{alert}\n```\n\n"
        f"@{commander_name} coordinate incident response: kick off the planner to "
        f"produce an incident plan, then the planner will consult documentation context "
        f"before handing to coder and reviewer."
    )
    client.send_message(chat_id, content, mentions=mentions)
    client.send_event(
        chat_id,
        f"Incident {incident_id} opened by watchdog",
        "task",
        metadata={"incident_id": incident_id, "status": "open"},
    )

    _active_incident = {"incident_id": incident_id, "chat_id": chat_id, "alert": alert}
    logger.info("Opened incident room %s (chat %s)", incident_id, chat_id)
    return _active_incident


def monitor_loop() -> None:
    global _active_incident
    load_dotenv()
    settings = get_settings()
    creds = load_agent_config("watchdog")
    target = settings.hosted_app_url or settings.demo_app_url

    clear_watchdog_context("startup")
    logger.info("Watchdog monitoring %s", target)

    with BandAgentClient(creds.agent_id, creds.api_key) as client:
        me = client.me()
        logger.info("Connected as %s", me.get("name", me.get("handle", creds.agent_id)))

        was_healthy = True
        consecutive_failures = 0
        threshold = max(1, settings.watchdog_failure_threshold)
        refresh_interval_s = max(0.0, settings.watchdog_context_refresh_s)
        last_refresh_at = time.monotonic()

        while True:
            last_refresh_at, refreshed, reset_failures = _maybe_refresh_context(
                client,
                last_refresh_at=last_refresh_at,
                refresh_interval_s=refresh_interval_s,
            )
            if reset_failures:
                consecutive_failures = 0
                was_healthy = True

            health = check_health()
            healthy = health.get("healthy", False)

            if healthy:
                consecutive_failures = 0
                if not was_healthy:
                    logger.info("Service recovered")
                    if _active_incident:
                        chat_id = str(_active_incident.get("chat_id") or "")
                        if chat_id and _incident_room_exists(client, chat_id):
                            client.send_event(
                                chat_id,
                                f"Service health restored for {_active_incident['incident_id']}",
                                "task",
                                metadata={"status": "resolved"},
                            )
                        clear_watchdog_context("service_recovered")
            else:
                consecutive_failures += 1
                reason = health.get("failure_reason") or classify_failure(health)
                if consecutive_failures < threshold:
                    logger.warning(
                        "Health check failed (%s): %s/%s before opening incident",
                        reason,
                        consecutive_failures,
                        threshold,
                    )
                elif not _active_incident:
                    logger.warning("Service unhealthy (%s); opening incident room", reason)
                    try:
                        open_incident_room(client, health)
                    except Exception:
                        logger.exception("Failed to open incident room")

            was_healthy = healthy
            time.sleep(settings.watchdog_poll_interval_s)
