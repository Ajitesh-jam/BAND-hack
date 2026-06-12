"""Tests for demo-app tool wrappers (no running server required for unit tests)."""

from __future__ import annotations

from app.chaos import ChaosState, FaultType


def test_chaos_activate_and_clear():
    state = ChaosState()
    state.activate(FaultType.BAD_CONFIG)
    assert state.active_fault == FaultType.BAD_CONFIG
    assert state.error_rate == 0.85
    state.clear()
    assert state.active_fault is None
    assert state.error_rate == 0.0


def test_chaos_to_dict():
    state = ChaosState()
    assert state.to_dict()["active_fault"] is None
    state.activate(FaultType.PII_LEAK)
    data = state.to_dict()
    assert data["active_fault"] == "pii_leak"
