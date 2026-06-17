"""Tests for orchestrator agent registration helpers."""

from __future__ import annotations

from band.tools import agent_registry_ops


def test_is_valid_credential_rejects_placeholder():
    assert not agent_registry_ops.is_valid_credential(
        {"agent_id": "00000000-0000-0000-0000-000000000001", "api_key": "key"}
    )
    assert agent_registry_ops.is_valid_credential(
        {"agent_id": "64d5b1e7-ee97-4f22-8f1e-1a5c32641dd8", "api_key": "band_a_real"}
    )


def test_register_agent_unknown_key():
    result = agent_registry_ops.register_agent("not_a_role")
    assert result["ok"] is False
