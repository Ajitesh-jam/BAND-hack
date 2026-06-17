"""Fault injection state for demo scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class FaultType(str, Enum):
    POOL_EXHAUSTION = "pool_exhaustion"
    PII_LEAK = "pii_leak"
    BAD_CONFIG = "bad_config"


@dataclass
class ChaosState:
    active_fault: FaultType | None = None
    activated_at: datetime | None = None
    leak_count: int = 0
    error_rate: float = 0.0
    held_connections: list[Any] = field(default_factory=list)

    def activate(self, fault: FaultType) -> None:
        self.clear()
        self.active_fault = fault
        self.activated_at = datetime.now(UTC)
        if fault == FaultType.BAD_CONFIG:
            self.error_rate = 0.85
        if fault == FaultType.PII_LEAK:
            self.leak_count = 0
        if fault == FaultType.POOL_EXHAUSTION:
            self._exhaust_connection_pool()

    def clear(self) -> None:
        for conn in self.held_connections:
            try:
                conn.close()
            except Exception:
                pass
        self.held_connections.clear()
        self.active_fault = None
        self.activated_at = None
        self.leak_count = 0
        self.error_rate = 0.0

    def _exhaust_connection_pool(self) -> None:
        from app.database import engine

        while True:
            try:
                conn = engine.connect()
                self.held_connections.append(conn)
            except Exception:
                break

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_fault": self.active_fault.value if self.active_fault else None,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "leak_count": self.leak_count,
            "error_rate": self.error_rate,
            "held_connections": len(self.held_connections),
        }


chaos = ChaosState()
