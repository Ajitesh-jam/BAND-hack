"""Tests for agent registry."""

from __future__ import annotations

import tempfile
from pathlib import Path

from band.registry import load_agent_config, save_agent_config


def test_load_agent_config_legacy_alias():
    agents = {
        "incident_commander": {
            "agent_id": "uuid-cmd",
            "api_key": "key-cmd",
            "handle": "@owner/incident-commander",
        }
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "agent_config.yaml"
        save_agent_config(agents, path)
        creds = load_agent_config("commander", path)
        assert creds.name == "commander"
        assert creds.agent_id == "uuid-cmd"
        assert creds.api_key == "key-cmd"


def test_save_and_load_agent_config():
    agents = {
        "watchdog": {
            "agent_id": "uuid-1",
            "api_key": "key-1",
            "handle": "watchdog",
        }
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "agent_config.yaml"
        save_agent_config(agents, path)
        creds = load_agent_config("watchdog", path)
        assert creds.agent_id == "uuid-1"
        assert creds.api_key == "key-1"
