"""Per-turn agent context.

The Gemini adapter records the room it is currently handling so that custom tools
(which only receive their validated input) can still discover the active room_id —
e.g. the human-approval tool needs to know which room to post the approval into.
"""

from __future__ import annotations

import contextvars

_current_room_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_room_id", default=None
)


def set_current_room(room_id: str | None) -> None:
    _current_room_id.set(room_id)


def get_current_room() -> str | None:
    return _current_room_id.get()
