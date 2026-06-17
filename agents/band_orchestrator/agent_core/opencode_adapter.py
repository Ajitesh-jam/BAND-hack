"""OpenCode adapter that exposes the active Band chat room_id to the model."""

from __future__ import annotations

from thenvoi.adapters import OpencodeAdapter
from thenvoi.core.protocols import AgentToolsProtocol
from thenvoi.core.types import PlatformMessage
from thenvoi.integrations.opencode import OpencodeSessionState

from agents.band_orchestrator.agent_core.room_context import set_active_room

_ROOM_ID_NOTE = (
    "\n[System]: Current chat room_id for ALL thenvoi_* tool calls "
    "(thenvoi_send_message, thenvoi_add_participant, etc.): {room_id}. "
    "This is NOT your agent_id — use this exact UUID as room_id.\n"
)


class OrchestratorOpencodeAdapter(OpencodeAdapter):
    """Sets active room context for deployagent and injects room_id into the prompt."""

    async def on_message(
        self,
        msg: PlatformMessage,
        tools: AgentToolsProtocol,
        history: OpencodeSessionState,
        participants_msg: str | None,
        contacts_msg: str | None,
        *,
        is_session_bootstrap: bool,
        room_id: str,
    ) -> None:
        set_active_room(room_id)
        room_participants = (participants_msg or "") + _ROOM_ID_NOTE.format(room_id=room_id)
        try:
            await super().on_message(
                msg,
                tools,
                history,
                room_participants,
                contacts_msg,
                is_session_bootstrap=is_session_bootstrap,
                room_id=room_id,
            )
        finally:
            set_active_room(None)
