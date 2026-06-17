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
    "band_orchestrator": {
        "name": "band-orchestrator",
        "description": "Spine agent — bootstraps team, routes incidents and features, gates merge.",
    },
    "company_agent": {
        "name": "company-agent",
        "description": "Graphify code graph + docs RAG over demo-app (orchestrator-managed).",
    },
    "watchdog": {
        "name": "watchdog",
        "description": "Monitors demo-app /health; opens incident rooms and alerts orchestrator.",
    },
    "planner": {
        "name": "planner",
        "description": "Produces structured implementation plans (OpenCode Nemotron).",
    },
    "planner_alpha": {
        "name": "planner-alpha",
        "description": "Sub-planner for large-repo partition A.",
    },
    "planner_beta": {
        "name": "planner-beta",
        "description": "Sub-planner for large-repo partition B.",
    },
    "coder": {
        "name": "coder",
        "description": "Implements plans via local git edits (OpenCode Nemotron).",
    },
    "reviewer": {
        "name": "reviewer",
        "description": "Reviews branch diffs and opens PRs (OpenCode Nemotron).",
    },
    "merger": {
        "name": "merger",
        "description": "Merges approved PRs and clears chaos.",
    },
}

DEFAULT_CONFIG_EXAMPLE = ROOT_DIR / "agent_config.yaml.example"
