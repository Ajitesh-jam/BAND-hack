"""Tests for orchestrator deploy_agent room recruitment."""

from __future__ import annotations

import json
from unittest.mock import patch

from agents.band_orchestrator.agent_core.room_context import set_active_room
from agents.band_orchestrator.agent_core.schema import DeployAgentInput
from agents.band_orchestrator.main import _deploy_agent


def test_deploy_agent_adds_per_task_role_to_active_room():
    set_active_room("room-abc")
    spawn_result = {"status": "deployed", "pid": 12345, "name": "planner"}

    with (
        patch("agents.band_orchestrator.main.process_manager.spawn", return_value=spawn_result),
        patch("agents.band_orchestrator.main.agent_registry_ops.ensure_agent_registered", return_value={"ok": True}),
        patch(
            "agents.band_orchestrator.main.load_agent_config",
            return_value=type("Creds", (), {"agent_id": "planner-id"})(),
        ),
        patch(
            "agents.band_orchestrator.main.add_agent_to_room",
            return_value={"ok": True, "chat_id": "room-abc", "participant_id": "planner-id"},
        ) as add_mock,
        patch(
            "agents.band_orchestrator.main.handoff_agent_in_room",
            return_value={"ok": True, "chat_id": "room-abc", "role": "planner"},
        ) as handoff_mock,
    ):
        payload = json.loads(_deploy_agent(DeployAgentInput(role="planner")))

    add_mock.assert_called_once_with("room-abc", "planner-id")
    handoff_mock.assert_called_once_with(
        "room-abc", "planner", "planner", partition=None, task=None
    )
    assert payload["room_add"]["ok"] is True
    set_active_room(None)


def test_deploy_agent_skips_room_add_for_persistent_agents():
    set_active_room("room-abc")
    spawn_result = {"status": "deployed", "pid": 99, "name": "watchdog"}

    with (
        patch("agents.band_orchestrator.main.process_manager.spawn", return_value=spawn_result),
        patch("agents.band_orchestrator.main.agent_registry_ops.ensure_agent_registered", return_value={"ok": True}),
        patch(
            "agents.band_orchestrator.main.load_agent_config",
            return_value=type("Creds", (), {"agent_id": "watchdog-id"})(),
        ),
        patch("agents.band_orchestrator.main.add_agent_to_room") as add_mock,
        patch("agents.band_orchestrator.main.handoff_agent_in_room") as handoff_mock,
    ):
        payload = json.loads(_deploy_agent(DeployAgentInput(role="watchdog")))

    add_mock.assert_not_called()
    handoff_mock.assert_not_called()
    assert payload["room_add"]["skipped"] is True
    set_active_room(None)


def test_deploy_agent_uses_explicit_chat_id():
    spawn_result = {"status": "deployed", "pid": 77, "name": "coder"}

    with (
        patch("agents.band_orchestrator.main.process_manager.spawn", return_value=spawn_result),
        patch("agents.band_orchestrator.main.agent_registry_ops.ensure_agent_registered", return_value={"ok": True}),
        patch(
            "agents.band_orchestrator.main.load_agent_config",
            return_value=type("Creds", (), {"agent_id": "coder-id"})(),
        ),
        patch(
            "agents.band_orchestrator.main.add_agent_to_room",
            return_value={"ok": True, "chat_id": "explicit-room", "participant_id": "coder-id"},
        ) as add_mock,
    ):
        payload = json.loads(
            _deploy_agent(DeployAgentInput(role="coder", chat_id="explicit-room"))
        )

    add_mock.assert_called_once_with("explicit-room", "coder-id")
    assert payload["room_add"]["ok"] is True
