"""Band REST API clients for Human and Agent perspectives.

Thin dict-returning wrappers over the typed `thenvoi_rest.RestClient`
that ships with band-sdk, so payload shapes always match the platform API.
"""

from __future__ import annotations

from typing import Any

from thenvoi_rest import (
    AgentRegisterRequest,
    ChatEventRequest,
    ChatMessageRequest,
    ChatMessageRequestMentionsItem,
    ChatRoomRequest,
    MemoryCreateRequest,
    ParticipantRequest,
    RestClient,
)
from thenvoi_rest.human_api_chats import CreateMyChatRoomRequestChat

from band.config import get_settings


def _dump(obj: Any) -> Any:
    """Convert Fern/pydantic response models to plain dicts/lists."""
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_dump(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj


def _mention_items(mentions: list[dict[str, Any]]) -> list[ChatMessageRequestMentionsItem]:
    return [
        ChatMessageRequestMentionsItem(
            id=m["id"],
            handle=m.get("handle"),
            name=m.get("name"),
        )
        for m in mentions
    ]


class BandHumanClient:
    """Human API client for agent registration and room management."""

    def __init__(self, api_key: str | None = None, rest_url: str | None = None) -> None:
        settings = get_settings()
        self._client = RestClient(
            base_url=(rest_url or settings.band_rest_url).rstrip("/"),
            api_key=api_key or settings.band_human_api_key,
        )

    def close(self) -> None:
        pass

    def __enter__(self) -> BandHumanClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def register_agent(self, name: str, description: str) -> dict[str, Any]:
        """Register a remote agent. Returns {"agent": {...}, "credentials": {"api_key": ...}}."""
        response = self._client.human_api_agents.register_my_agent(
            agent=AgentRegisterRequest(name=name, description=description),
        )
        data = _dump(response)
        return data.get("data", data)

    def list_agents(self) -> list[dict[str, Any]]:
        response = self._client.human_api_agents.list_my_agents()
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data

    def create_chat(self, task_id: str | None = None) -> dict[str, Any]:
        chat = (
            CreateMyChatRoomRequestChat(task_id=task_id)
            if task_id
            else CreateMyChatRoomRequestChat()
        )
        response = self._client.human_api_chats.create_my_chat_room(chat=chat)
        data = _dump(response)
        return data.get("data", data)

    def add_participant(self, chat_id: str, participant_id: str) -> dict[str, Any]:
        response = self._client.human_api_participants.add_my_chat_participant(
            chat_id,
            participant=ParticipantRequest(participant_id=participant_id),
        )
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data

    def send_message(
        self,
        chat_id: str,
        content: str,
        mentions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Send a text message. Mentions are required: [{"id": ..., "handle": ..., "name": ...}]."""
        response = self._client.human_api_messages.send_my_chat_message(
            chat_id,
            message=ChatMessageRequest(content=content, mentions=_mention_items(mentions)),
        )
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data


class BandAgentClient:
    """Agent API client for programmatic room operations (Watchdog, tools)."""

    def __init__(self, agent_id: str, api_key: str, rest_url: str | None = None) -> None:
        settings = get_settings()
        self.agent_id = agent_id
        self._client = RestClient(
            base_url=(rest_url or settings.band_rest_url).rstrip("/"),
            api_key=api_key,
        )

    def close(self) -> None:
        pass

    def __enter__(self) -> BandAgentClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def me(self) -> dict[str, Any]:
        data = _dump(self._client.agent_api_identity.get_agent_me())
        return data.get("data", data)

    def create_chat(self, task_id: str | None = None) -> dict[str, Any]:
        chat = ChatRoomRequest(task_id=task_id) if task_id else ChatRoomRequest()
        response = self._client.agent_api_chats.create_agent_chat(chat=chat)
        data = _dump(response)
        return data.get("data", data)

    def get_chat_context(self, chat_id: str) -> dict[str, Any]:
        data = _dump(self._client.agent_api_context.get_agent_chat_context(chat_id))
        return data.get("data", data) if isinstance(data, dict) else data

    def list_peers(self, not_in_chat: str | None = None) -> list[dict[str, Any]]:
        response = self._client.agent_api_peers.list_agent_peers(not_in_chat=not_in_chat)
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data

    def add_participant(self, chat_id: str, participant_id: str) -> dict[str, Any]:
        response = self._client.agent_api_participants.add_agent_chat_participant(
            chat_id,
            participant=ParticipantRequest(participant_id=participant_id),
        )
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data

    def remove_participant(self, chat_id: str, participant_id: str) -> dict[str, Any]:
        response = self._client.agent_api_participants.remove_agent_chat_participant(
            chat_id, participant_id
        )
        data = _dump(response)
        return data if isinstance(data, dict) else {}

    def send_message(
        self,
        chat_id: str,
        content: str,
        mentions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Send a text message. Mentions are required: [{"id": ..., "handle": ..., "name": ...}]."""
        response = self._client.agent_api_messages.create_agent_chat_message(
            chat_id,
            message=ChatMessageRequest(content=content, mentions=_mention_items(mentions)),
        )
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data

    def send_event(
        self,
        chat_id: str,
        content: str,
        message_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.agent_api_events.create_agent_chat_event(
            chat_id,
            event=ChatEventRequest(content=content, message_type=message_type, metadata=metadata),
        )
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data

    def list_memories(self, content_query: str | None = None) -> list[dict[str, Any]]:
        response = self._client.agent_api_memories.list_agent_memories(content_query=content_query)
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data

    def store_memory(
        self,
        content: str,
        system: str = "long_term",
        type_: str = "episodic",
        segment: str = "agent",
        thought: str = "incident resolved",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a memory. system: sensory|working|long_term, type: episodic|semantic|procedural|...,
        segment: user|agent|tool|guideline."""
        response = self._client.agent_api_memories.create_agent_memory(
            memory=MemoryCreateRequest(
                content=content,
                system=system,
                type=type_,
                segment=segment,
                thought=thought,
                metadata=metadata,
            ),
        )
        data = _dump(response)
        return data.get("data", data) if isinstance(data, dict) else data
