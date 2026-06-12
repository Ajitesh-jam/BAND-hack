"""Memory operations for scribe and commander."""

from __future__ import annotations

from typing import Any

from band.client import BandAgentClient
from band.registry import load_agent_config


def recall_similar_incidents(query: str, agent_name: str = "incident_commander") -> list[dict[str, Any]]:
    creds = load_agent_config(agent_name)
    with BandAgentClient(creds.agent_id, creds.api_key) as client:
        return client.list_memories(content_query=query)


def store_incident_memory(
    content: str,
    incident_id: str,
    agent_name: str = "scribe",
) -> dict[str, Any]:
    creds = load_agent_config(agent_name)
    with BandAgentClient(creds.agent_id, creds.api_key) as client:
        return client.store_memory(
            content=content,
            metadata={"incident_id": incident_id},
            thought=f"postmortem for {incident_id}",
        )


def fetch_room_context(chat_id: str, agent_name: str = "scribe") -> dict[str, Any]:
    creds = load_agent_config(agent_name)
    with BandAgentClient(creds.agent_id, creds.api_key) as client:
        return client.get_chat_context(chat_id)
