"""Load agent credentials from agent_config.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from band.config import ROOT_DIR, get_settings


@dataclass(frozen=True)
class AgentCredentials:
    name: str
    agent_id: str
    api_key: str
    handle: str | None = None


def load_agent_config(name: str, path: Path | None = None) -> AgentCredentials:
    config_path = path or get_settings().agent_config_path
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing {config_path}. Copy agent_config.yaml.example and run scripts/setup_agents.py"
        )
    with config_path.open() as f:
        data = yaml.safe_load(f) or {}
    if name not in data:
        raise KeyError(f"Agent '{name}' not found in {config_path}")
    entry = data[name]
    return AgentCredentials(
        name=name,
        agent_id=entry["agent_id"],
        api_key=entry["api_key"],
        handle=entry.get("handle"),
    )


def save_agent_config(agents: dict[str, dict[str, str]], path: Path | None = None) -> Path:
    config_path = path or get_settings().agent_config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w") as f:
        yaml.safe_dump(agents, f, default_flow_style=False, sort_keys=True)
    return config_path


AGENT_DEFINITIONS: dict[str, dict[str, str]] = {
    "watchdog": {
        "name": "watchdog",
        "description": "Monitors demo-app health and opens incident rooms on failure.",
    },
    "incident_commander": {
        "name": "incident-commander",
        "description": "Classifies incidents, recruits specialists, coordinates response.",
    },
    "log_analyst": {
        "name": "log-analyst",
        "description": "Analyzes logs and telemetry to identify root cause.",
    },
    "fix_engineer": {
        "name": "fix-engineer",
        "description": "Proposes patches and opens GitHub pull requests.",
    },
    "reviewer": {
        "name": "reviewer",
        "description": "Cross-model reviewer for proposed fixes.",
    },
    "compliance_officer": {
        "name": "compliance-officer",
        "description": "Assesses regulatory impact when PII or security issues are detected.",
    },
    "scribe": {
        "name": "scribe",
        "description": "Generates postmortems and stores institutional memory.",
    },
}

DEFAULT_CONFIG_EXAMPLE = ROOT_DIR / "agent_config.yaml.example"
