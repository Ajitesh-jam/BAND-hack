"""Track the Band chat room currently being handled by the orchestrator."""

from __future__ import annotations

_active_room_id: str | None = None


def set_active_room(room_id: str | None) -> None:
    global _active_room_id
    _active_room_id = room_id


def get_active_room() -> str | None:
    return _active_room_id
