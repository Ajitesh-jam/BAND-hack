"""Band Orchestrator agent — builds and deploys other Band agents on demand.

Same shape as every other agent in this repo: it builds a Band SDK adapter
(via the shared ``adapter_sdk``, gemini by default) with a set of custom tools,
then runs through ``create_and_run``. The tools generate/convert agent code and
launch each new agent as its own subprocess.
"""

from __future__ import annotations

import json
import logging
import uuid

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.config import ROOT_DIR
from band.prompts import ORCHESTRATOR_PROMPT
from band.tools import github_ops

from agents.band_orchestrator.agent_core import converter, generator
from agents.band_orchestrator.agent_core import company_agent
from agents.band_orchestrator.agent_core.process_runner import process_manager
from agents.band_orchestrator.agent_core.schema import (
    BuildCompanyContextInput,
    ConvertAgentInput,
    CreateBandAgentInput,
    CreateCompanyContextAgentInput,
    DeployCompanyContextAgentInput,
    ListGeneratedAgentsInput,
    MakeCompanyAgentsInput,
    PublishAgentInput,
    StopGeneratedAgentInput,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [orchestrator] %(message)s")
logger = logging.getLogger(__name__)


def _create_band_agent(inp: CreateBandAgentInput) -> str:
    try:
        meta = generator.create_agent(
            description=inp.description,
            agent_id=inp.agent_id,
            api_key=inp.api_key,
            name=inp.name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_agent failed")
        return json.dumps({"status": "failed", "error": str(exc)})

    result = process_manager.spawn(
        name=meta["name"],
        script_path=meta["main_path"],
        cwd=meta["folder"],
        log_path=f"{meta['folder']}/agent.log",
    )
    result.update({"agent_id": meta["agent_id"], "folder": meta["folder"]})
    result["next_step"] = (
        f"Call thenvoi_add_participant with agent_id={meta['agent_id']} to bring "
        f"'{meta['name']}' into this room."
    )
    return json.dumps(result)


def _convert_agent(inp: ConvertAgentInput) -> str:
    try:
        meta = converter.convert_agent(
            folder_path=inp.folder_path,
            agent_id=inp.agent_id,
            api_key=inp.api_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("convert_agent failed")
        return json.dumps({"status": "failed", "error": str(exc)})

    if meta.get("status") != "success":
        return json.dumps(meta)

    base = generator._slugify(inp.folder_path.rstrip("/").split("/")[-1])
    name = f"converted_{base}_{uuid.uuid4().hex[:8]}"
    log_path = f"{meta['folder']}/band_integration.log"
    result = process_manager.spawn(
        name=name,
        script_path=meta["integration_path"],
        cwd=meta["folder"],
        log_path=log_path,
    )
    result.update({"agent_id": meta["agent_id"], "folder": meta["folder"]})
    result["next_step"] = (
        f"Call thenvoi_add_participant with agent_id={meta['agent_id']} to bring "
        f"'{name}' into this room."
    )
    return json.dumps(result)


def _list_agents(_: ListGeneratedAgentsInput) -> str:
    return json.dumps({"agents": process_manager.list_agents()})


def _stop_agent(inp: StopGeneratedAgentInput) -> str:
    return json.dumps(process_manager.stop(inp.name))


def _publish_agent(inp: PublishAgentInput) -> str:
    folder = process_manager.folder_for(inp.name)
    if not folder:
        candidate = ROOT_DIR / "generated_agents" / inp.name
        folder = str(candidate) if candidate.exists() else None
    if not folder:
        return json.dumps({"ok": False, "error": f"unknown agent '{inp.name}'"})
    try:
        return json.dumps(
            github_ops.publish_agent_pr(folder, title=inp.title, body=inp.body)
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("publish_agent failed")
        return json.dumps({"ok": False, "error": str(exc)})


def _create_company_context_agent(inp: CreateCompanyContextAgentInput) -> str:
    try:
        result = company_agent.scaffold_company_agent(
            agent_id=inp.agent_id,
            api_key=inp.api_key,
            name=inp.name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("scaffold_company_agent failed")
        return json.dumps({"status": "failed", "error": str(exc)})
    return json.dumps(result)


def _build_company_context(inp: BuildCompanyContextInput) -> str:
    try:
        result = company_agent.build_company_context(
            name=inp.name,
            github_url=inp.github_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_company_context failed")
        return json.dumps({"status": "failed", "error": str(exc)})
    return json.dumps(result)


def _deploy_company_context_agent(inp: DeployCompanyContextAgentInput) -> str:
    try:
        meta = company_agent.deploy_company_agent(inp.name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("deploy_company_agent failed")
        return json.dumps({"status": "failed", "error": str(exc)})

    if not meta.get("ok"):
        return json.dumps(meta)

    result = process_manager.spawn(
        name=meta["name"],
        script_path=meta["main_path"],
        cwd=meta["folder"],
        log_path=f"{meta['folder']}/agent.log",
    )
    result.update({"agent_id": meta["agent_id"], "folder": meta["folder"]})
    result["next_step"] = (
        f"Call thenvoi_add_participant with agent_id={meta['agent_id']} to bring "
        f"'{meta['name']}' into this room."
    )
    return json.dumps(result)


def _make_company_agents(inp: MakeCompanyAgentsInput) -> str:
    try:
        meta = company_agent.deploy_company_roster(
            github_url=inp.github_url,
            hosted_link=inp.hosted_link,
            github_token=inp.github_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("make_company_agents failed")
        return json.dumps({"status": "failed", "error": str(exc)})

    spawned: dict[str, dict] = {}
    for role, agent_meta in meta.get("agents", {}).items():
        main_path = agent_meta.get("main_path")
        folder = agent_meta.get("folder")
        if not main_path or not folder:
            spawned[role] = {"status": "error", "message": "missing main_path or folder"}
            continue
        result = process_manager.spawn(
            name=role,
            script_path=main_path,
            cwd=folder,
            log_path=agent_meta.get("log_path"),
        )
        result.update({"agent_id": agent_meta.get("agent_id"), "folder": folder})
        spawned[role] = result

    meta["spawned"] = spawned
    meta["room_next_steps"] = [
        {
            "role": role,
            "agent_id": result.get("agent_id"),
            "action": "call thenvoi_add_participant with this agent_id",
        }
        for role, result in spawned.items()
        if result.get("agent_id")
    ]
    meta["usage"] = (
        "Company agents deployed. For features, bring commander/planner/coder/reviewer/"
        "documentation_agent into a room and ask commander. For incidents, watchdog monitors "
        "the hosted link and opens a room on health failures."
    )
    return json.dumps(meta)


def _custom_tools() -> list[CustomToolDef]:
    return [
        (CreateBandAgentInput, _create_band_agent),
        (ConvertAgentInput, _convert_agent),
        (ListGeneratedAgentsInput, _list_agents),
        (StopGeneratedAgentInput, _stop_agent),
        (PublishAgentInput, _publish_agent),
        (CreateCompanyContextAgentInput, _create_company_context_agent),
        (BuildCompanyContextInput, _build_company_context),
        (DeployCompanyContextAgentInput, _deploy_company_context_agent),
        (MakeCompanyAgentsInput, _make_company_agents),
    ]


STARTUP_BRIEF = (
    "Hi, I'm the Band Orchestrator. Here's what I can do:\n"
    "- Create a single Band agent on demand.\n"
    "- Make a full team of company Band agents to manage your codebase.\n\n"
    "Say \"make company agents\" and I'll deploy a watchdog, documentation_agent, "
    "commander, planner, coder, and reviewer for your repo. I'll ask for your GitHub "
    "repo URL, hosted app link, and (optionally) a GitHub token for PRs."
)


def build_adapter():
    return adapter_sdk(
        ORCHESTRATOR_PROMPT,
        additional_tools=_custom_tools(),
        enable_memory=True,
    )


def cli() -> None:
    create_and_run(build_adapter(), "band_orchestrator", "Band Orchestrator")


if __name__ == "__main__":
    cli()
