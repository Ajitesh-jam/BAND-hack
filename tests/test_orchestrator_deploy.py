"""Tests for orchestrator deployagent tool."""

from __future__ import annotations

import json
from unittest.mock import patch

from agents.band_orchestrator.agent_core.schema import DeployAgentInput
from agents.band_orchestrator.main import _deploy_agent


def test_deploy_agent_spawns_and_returns_agent_id():
    spawn_result = {"status": "deployed", "pid": 12345, "name": "coder"}

    with (
        patch("agents.band_orchestrator.main.process_manager.spawn", return_value=spawn_result),
        patch("agents.band_orchestrator.main.agent_registry_ops.ensure_agent_registered", return_value={"ok": True}),
        patch(
            "agents.band_orchestrator.main.load_agent_config",
            return_value=type("Creds", (), {"agent_id": "coder-id"})(),
        ),
    ):
        payload = json.loads(_deploy_agent(DeployAgentInput(role="coder")))

    assert payload["agent_id"] == "coder-id"
    assert payload["status"] == "deployed"
    assert "thenvoi_add_participant" in payload["next_step"]


def test_deploy_agent_unknown_role():
    payload = json.loads(_deploy_agent(DeployAgentInput(role="not_a_role")))
    assert payload["status"] == "failed"
