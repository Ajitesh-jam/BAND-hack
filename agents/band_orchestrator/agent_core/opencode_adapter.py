"""OpenCode adapter with active-room tracking for orchestrator custom tools."""

from __future__ import annotations

from thenvoi.adapters import OpencodeAdapter
from thenvoi.core.protocols import AgentToolsProtocol
from thenvoi.core.types import PlatformMessage
from thenvoi.integrations.opencode import OpencodeSessionState

from agents.band_orchestrator.agent_core.room_context import set_active_room


class OrchestratorOpencodeAdapter(OpencodeAdapter):
    """Keeps the current incident room id available to deploy_agent handlers."""

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
        try:
            await super().on_message(
                msg,
                tools,
                history,
                participants_msg,
                contacts_msg,
                is_session_bootstrap=is_session_bootstrap,
                room_id=room_id,
            )
        finally:
            set_active_room(None)
