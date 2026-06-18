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
    "commander": {
        "name": "commander",
        "description": "Coordinates company-agent feature and incident workflows.",
    },
    "planner": {
        "name": "planner",
        "description": "Builds implementation and incident-resolution plans using documentation context.",
    },
    "documentation_agent": {
        "name": "documentation-agent",
        "description": "Answers codebase, docs, dependency graph, and commit-history questions.",
    },
    "coder": {
        "name": "coder",
        "description": "Implements plans and verifies health; delegates git/GitHub to github_agent.",
    },
    "reviewer": {
        "name": "reviewer",
        "description": "Reviews code changes and returns bounded APPROVE or REQUEST_CHANGES verdicts.",
    },
    "github_agent": {
        "name": "github-agent",
        "description": "Pushes approved changes and opens GitHub PRs after human approval.",
    },
    "band_orchestrator": {
        "name": "band-orchestrator",
        "description": "Builds and deploys new Band agents on demand and brings them into rooms.",
    },
}

DEFAULT_CONFIG_EXAMPLE = ROOT_DIR / "agent_config.yaml.example"
