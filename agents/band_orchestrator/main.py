"""Band Orchestrator — spine that bootstraps the dev team and routes tasks."""

from __future__ import annotations

import json
import logging
import sys

from thenvoi.runtime.custom_tools import CustomToolDef

from agents.band_orchestrator.agent_core.context_engine import build_context
from agents.band_orchestrator.agent_core.process_runner import process_manager
from agents.band_orchestrator.agent_core.schema import (
    BuildContextInput,
    DeployAgentInput,
    GetContextPathsInput,
    ListAgentsInput,
    RegisterAgentInput,
    RegisterTeamInput,
    StopAgentInput,
)
from band.agents.base import create_and_run
from band.agents.sdk.opencode_sdk import opencode_agent
from band.config import ROOT_DIR, get_settings
from band.prompts import ORCHESTRATOR_PROMPT
from band.registry import load_agent_config
from band.tools import agent_registry_ops, graphify_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s [orchestrator] %(message)s")
logger = logging.getLogger(__name__)

ROLE_MODULES: dict[str, tuple[str, str]] = {
    "company_agent": ("agents.company_agent.main", "company_agent"),
    "watchdog": ("agents.watchdog.main", "watchdog"),
    "planner": ("agents.planner.main", "planner"),
    "planner_alpha": ("agents.planner.main", "planner_alpha"),
    "planner_beta": ("agents.planner.main", "planner_beta"),
    "coder": ("agents.coder.main", "coder"),
    "reviewer": ("agents.reviewer.main", "reviewer"),
    "merger": ("agents.merger.main", "merger"),
}

PERSISTENT_ROLES = ("company_agent", "watchdog")


def _deploy_agent(inp: DeployAgentInput) -> str:
    role = inp.role.strip().lower()
    if role not in ROLE_MODULES:
        return json.dumps({"status": "failed", "error": f"unknown role: {inp.role}"})

    module, config_key = ROLE_MODULES[role]

    reg = agent_registry_ops.ensure_agent_registered(config_key)
    if not reg.get("ok"):
        return json.dumps({"status": "failed", "role": role, "error": reg.get("error"), "register": reg})

    settings = get_settings()
    log_dir = settings.workspace_dir / "agents"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(log_dir / f"{role}.log")

    extra_env: dict[str, str] = {"BAND_CONFIG_KEY": config_key}
    if inp.partition and role in ("planner_alpha", "planner_beta"):
        extra_env["BAND_PLANNER_PARTITION"] = inp.partition

    result = process_manager.spawn(
        name=role,
        cwd=str(ROOT_DIR),
        log_path=log_path,
        cmd=[sys.executable, "-m", module],
        extra_env=extra_env,
    )

    try:
        creds = load_agent_config(config_key)
        agent_id = creds.agent_id
    except (FileNotFoundError, KeyError) as exc:
        return json.dumps({**result, "status": "failed", "error": str(exc)})

    result["agent_id"] = agent_id
    result["role"] = role
    result["config_key"] = config_key
    result["next_step"] = (
        f"Call thenvoi_add_participant with participant_id={agent_id}, "
        f"then thenvoi_send_message to @mention and task '{role}'."
    )
    return json.dumps(result)


def _list_agents(_: ListAgentsInput) -> str:
    return json.dumps({"agents": process_manager.list_agents()})


def _stop_agent(inp: StopAgentInput) -> str:
    return json.dumps(process_manager.stop(inp.name))


def _build_context(inp: BuildContextInput) -> str:
    try:
        return json.dumps(build_context(inp.target_path))
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_context failed")
        return json.dumps({"ok": False, "error": str(exc)})


def _get_context_paths(inp: GetContextPathsInput) -> str:
    return json.dumps(graphify_ops.context_paths(inp.target_path))


def _register_agent(inp: RegisterAgentInput) -> str:
    return json.dumps(agent_registry_ops.register_agent(inp.role.strip().lower(), force=inp.force))


def _register_team(inp: RegisterTeamInput) -> str:
    return json.dumps(agent_registry_ops.register_team(force=inp.force))


def _custom_tools() -> list[CustomToolDef]:
    return [
        (RegisterAgentInput, _register_agent),
        (RegisterTeamInput, _register_team),
        (DeployAgentInput, _deploy_agent),
        (ListAgentsInput, _list_agents),
        (StopAgentInput, _stop_agent),
        (BuildContextInput, _build_context),
        (GetContextPathsInput, _get_context_paths),
    ]


def bootstrap_startup() -> None:
    """Deterministic context build + deploy persistent agents (no LLM)."""
    settings = get_settings()
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Building company context (graphify + docs RAG)...")
    ctx = build_context()
    logger.info("Context build ok=%s graph=%s docs=%s", ctx.get("ok"), ctx.get("graph", {}).get("ok"), ctx.get("docs", {}).get("ok"))

    logger.info("Ensuring team agents are registered on Band (agent_config.yaml)...")
    team_reg = agent_registry_ops.register_team()
    logger.info(
        "Team registration: registered=%s already=%s failed=%s",
        team_reg.get("registered"),
        team_reg.get("already_configured"),
        team_reg.get("failed"),
    )
    if team_reg.get("failed"):
        for item in team_reg.get("results", []):
            if not item.get("ok"):
                logger.warning("Registration failed for %s: %s", item.get("config_key"), item.get("error"))

    for role in PERSISTENT_ROLES:
        logger.info("Deploying persistent agent: %s", role)
        payload = json.loads(_deploy_agent(DeployAgentInput(role=role)))
        if payload.get("status") in ("deployed", "already_running"):
            logger.info("%s: pid=%s agent_id=%s", role, payload.get("pid"), payload.get("agent_id"))
        else:
            logger.warning("Failed to deploy %s: %s", role, payload)


def build_adapter():
    settings = get_settings()
    return opencode_agent(
        ORCHESTRATOR_PROMPT,
        settings.orchestrator_model,
        additional_tools=_custom_tools(),
        enable_memory=True,
        permission_mode="bypassPermissions",
    )


def cli() -> None:
    bootstrap_startup()
    create_and_run(build_adapter(), "band_orchestrator", "Band Orchestrator")


if __name__ == "__main__":
    cli()
