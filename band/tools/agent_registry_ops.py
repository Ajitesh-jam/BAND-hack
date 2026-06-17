"""Band agent registration and agent_config.yaml management for the orchestrator."""

from __future__ import annotations

import logging
from typing import Any

import yaml

from band.client import BandHumanClient
from band.config import get_settings
from band.registry import AGENT_DEFINITIONS, save_agent_config

logger = logging.getLogger(__name__)

PLACEHOLDER_PREFIXES = ("00000000-0000-0000-0000-", "your-")


def load_config_dict() -> dict[str, dict[str, str]]:
    path = get_settings().agent_config_path
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def is_valid_credential(entry: dict[str, str] | None) -> bool:
    if not entry:
        return False
    agent_id = entry.get("agent_id", "")
    api_key = entry.get("api_key", "")
    if not agent_id or not api_key:
        return False
    if any(agent_id.startswith(p) for p in PLACEHOLDER_PREFIXES):
        return False
    if api_key.startswith("your-"):
        return False
    return True


def register_agent(config_key: str, *, force: bool = False) -> dict[str, Any]:
    """Register one agent on Band and upsert credentials into agent_config.yaml."""
    if config_key not in AGENT_DEFINITIONS:
        return {"ok": False, "error": f"unknown config key: {config_key}"}

    spec = AGENT_DEFINITIONS[config_key]
    config = load_config_dict()

    if not force and is_valid_credential(config.get(config_key)):
        entry = config[config_key]
        return {
            "ok": True,
            "status": "already_configured",
            "config_key": config_key,
            "agent_id": entry["agent_id"],
            "handle": entry.get("handle", spec["name"]),
        }

    settings = get_settings()
    if not settings.band_human_api_key:
        return {"ok": False, "error": "BAND_HUMAN_API_KEY not set — cannot register agents"}

    try:
        with BandHumanClient() as client:
            existing_by_name = {a.get("name", ""): a for a in client.list_agents()}
            if spec["name"] in existing_by_name and not force:
                agent = existing_by_name[spec["name"]]
                return {
                    "ok": False,
                    "status": "exists_on_band",
                    "config_key": config_key,
                    "band_name": spec["name"],
                    "band_agent_id": agent.get("id"),
                    "error": (
                        f"Agent '{spec['name']}' already exists on Band but creds missing "
                        f"from agent_config.yaml — add api_key manually or use force=true"
                    ),
                }

            result = client.register_agent(spec["name"], spec["description"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("register_agent failed for %s", config_key)
        return {"ok": False, "config_key": config_key, "error": str(exc)}

    agent_info = result.get("agent") or {}
    credentials = result.get("credentials") or {}
    agent_id = agent_info.get("id") or result.get("id")
    api_key = credentials.get("api_key") or result.get("api_key")
    if not agent_id or not api_key:
        return {
            "ok": False,
            "config_key": config_key,
            "error": f"unexpected Band response: {result}",
        }

    config[config_key] = {
        "agent_id": agent_id,
        "api_key": api_key,
        "handle": spec["name"],
    }
    path = save_agent_config(config)
    logger.info("Registered %s → %s (wrote %s)", config_key, agent_id, path)
    return {
        "ok": True,
        "status": "registered",
        "config_key": config_key,
        "agent_id": agent_id,
        "handle": spec["name"],
        "config_path": str(path),
    }


def register_team(*, skip_orchestrator: bool = True, force: bool = False) -> dict[str, Any]:
    """Register all team agents missing from agent_config.yaml."""
    keys = [
        k for k in AGENT_DEFINITIONS if not (skip_orchestrator and k == "band_orchestrator")
    ]
    results: list[dict[str, Any]] = []
    for key in keys:
        results.append(register_agent(key, force=force))
    ok = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]
    return {
        "ok": len(failed) == 0,
        "registered": len([r for r in ok if r.get("status") == "registered"]),
        "already_configured": len([r for r in ok if r.get("status") == "already_configured"]),
        "failed": len(failed),
        "results": results,
    }


def ensure_agent_registered(config_key: str) -> dict[str, Any]:
    """Register agent if missing; used before deploy_agent."""
    config = load_config_dict()
    if is_valid_credential(config.get(config_key)):
        entry = config[config_key]
        return {
            "ok": True,
            "status": "ready",
            "config_key": config_key,
            "agent_id": entry["agent_id"],
        }
    return register_agent(config_key)
