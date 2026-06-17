"""Add deployed agents to the active Band incident room and send handoff messages."""

from __future__ import annotations

import logging
from typing import Any

from band.client import BandAgentClient
from band.registry import AgentCredentials, load_agent_config
from band.tools import graphify_ops

logger = logging.getLogger(__name__)

ROLE_HANDLES: dict[str, str] = {
    "planner": "planner",
    "planner_alpha": "planner-alpha",
    "planner_beta": "planner-beta",
    "coder": "coder",
    "reviewer": "reviewer",
    "merger": "merger",
}


def _orchestrator_client() -> BandAgentClient:
    creds = load_agent_config("band_orchestrator")
    return BandAgentClient(creds.agent_id, creds.api_key)


def _mention(creds: AgentCredentials, role: str) -> list[dict[str, str]]:
    handle = creds.handle or ROLE_HANDLES.get(role, role)
    return [{"id": creds.agent_id, "handle": handle, "name": handle}]


def add_agent_to_room(chat_id: str, participant_agent_id: str) -> dict[str, Any]:
    """Add an agent to a chat room using orchestrator credentials."""
    client = _orchestrator_client()
    try:
        result = client.add_participant(chat_id, participant_agent_id)
        return {"ok": True, "chat_id": chat_id, "participant_id": participant_agent_id, "result": result}
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        lowered = message.lower()
        if "already" in lowered or "duplicate" in lowered or "409" in lowered:
            logger.info("Agent %s already in room %s", participant_agent_id, chat_id)
            return {
                "ok": True,
                "chat_id": chat_id,
                "participant_id": participant_agent_id,
                "already_in_room": True,
            }
        logger.warning("Failed to add %s to room %s: %s", participant_agent_id, chat_id, exc)
        return {"ok": False, "chat_id": chat_id, "participant_id": participant_agent_id, "error": message}


def _default_handoff(role: str, creds: AgentCredentials, *, partition: str | None = None) -> str:
    handle = creds.handle or ROLE_HANDLES.get(role, role)
    if role == "planner":
        paths = graphify_ops.context_paths()
        return (
            f"@{handle} — analyze the watchdog alert in this room and produce a structured "
            f"fix plan for demo-app (pool_exhaustion / checkout-api).\n\n"
            f"Context paths:\n"
            f"- graph: {paths['graph_json']}\n"
            f"- docs index: {paths['docs_index']}\n\n"
            f"Use @company-agent for architecture questions. Call emit_plan when ready, "
            f"then @band-orchestrator-agent."
        )
    if role in ("planner_alpha", "planner_beta"):
        scope = partition or "your assigned partition"
        return (
            f"@{handle} — plan changes for partition only:\n{scope}\n\n"
            f"Consult @company-agent for file dependencies. Emit sub-plan via emit_plan, "
            f"then @band-orchestrator-agent."
        )
    if role == "coder":
        return (
            f"@{handle} — implement the approved plan in this room against demo-app. "
            f"Post branch name when done, then @reviewer."
        )
    if role == "reviewer":
        return (
            f"@{handle} — review the branch posted in this room. Open a PR if clean, "
            f"otherwise loop with @coder or @planner."
        )
    if role == "merger":
        return f"@{handle} — merge the approved PR URL shared in this room after human sign-off."
    return f"@{handle} — please pick up the task in this room."


def handoff_agent_in_room(
    chat_id: str,
    role: str,
    config_key: str,
    *,
    partition: str | None = None,
    task: str | None = None,
) -> dict[str, Any]:
    """@mention the deployed agent with a deterministic handoff message."""
    creds = load_agent_config(config_key)
    content = (task or "").strip() or _default_handoff(role, creds, partition=partition)
    client = _orchestrator_client()
    try:
        message = client.send_message(chat_id, content, mentions=_mention(creds, role))
        return {"ok": True, "chat_id": chat_id, "role": role, "message_id": message.get("id")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to hand off to %s in room %s: %s", role, chat_id, exc)
        return {"ok": False, "chat_id": chat_id, "role": role, "error": str(exc)}
