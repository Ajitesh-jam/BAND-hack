"""In-memory log ring buffer for /logs endpoint."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

_MAX_LOGS = 500
_buffer: deque[dict[str, Any]] = deque(maxlen=_MAX_LOGS)


def append_log(level: str, message: str, **extra: Any) -> None:
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "message": message,
        **extra,
    }
    _buffer.append(entry)


def get_logs(limit: int = 100, level: str | None = None) -> list[dict[str, Any]]:
    logs = list(_buffer)
    if level:
        logs = [log for log in logs if log.get("level") == level.upper()]
    return logs[-limit:]
