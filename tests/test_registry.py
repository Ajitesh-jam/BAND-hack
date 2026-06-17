"""Tests for agent registry."""

from __future__ import annotations

import tempfile
from pathlib import Path

from band.registry import AGENT_DEFINITIONS, load_agent_config, save_agent_config


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


def test_agent_definitions_keys():
    expected = {
        "band_orchestrator",
        "company_agent",
        "watchdog",
        "planner",
        "planner_alpha",
        "planner_beta",
        "coder",
        "reviewer",
        "merger",
    }
    assert set(AGENT_DEFINITIONS) == expected
