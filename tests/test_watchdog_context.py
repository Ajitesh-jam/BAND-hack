"""Tests for watchdog context lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.watchdog.agent_core import helper


def setup_function() -> None:
    helper.clear_watchdog_context("test_reset")


def test_clear_watchdog_context():
    helper._active_incident = {
        "incident_id": "INC-0618-001",
        "chat_id": "room-1",
    }
    helper.clear_watchdog_context("manual")
    assert helper.get_active_incident() is None


def test_refresh_on_deleted_room():
    helper._active_incident = {
        "incident_id": "INC-0618-001",
        "chat_id": "deleted-room",
    }
    client = MagicMock()
    client.get_chat_context.side_effect = RuntimeError("404")

    with patch("agents.watchdog.agent_core.helper.time.monotonic", return_value=60.0):
        last, _cleared, reset = helper._maybe_refresh_context(
            client,
            last_refresh_at=0.0,
            refresh_interval_s=300.0,
        )

    assert helper.get_active_incident() is None
    assert reset is True
    assert last == 0.0


def test_scheduled_refresh_clears_active_incident():
    helper._active_incident = {
        "incident_id": "INC-0618-002",
        "chat_id": "room-2",
    }
    client = MagicMock()
    client.get_chat_context.return_value = {"id": "room-2"}

    with patch("agents.watchdog.agent_core.helper.time.monotonic", return_value=400.0):
        last, _cleared, reset = helper._maybe_refresh_context(
            client,
            last_refresh_at=0.0,
            refresh_interval_s=300.0,
        )

    assert helper.get_active_incident() is None
    assert reset is True
    assert last == 400.0


def test_room_exists_when_context_available():
    client = MagicMock()
    client.get_chat_context.return_value = {"id": "room-1"}
    assert helper._incident_room_exists(client, "room-1") is True


def test_room_missing_when_context_raises():
    client = MagicMock()
    client.get_chat_context.side_effect = Exception("not found")
    assert helper._incident_room_exists(client, "gone") is False
