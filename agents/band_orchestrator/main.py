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
from agents.band_orchestrator.agent_core.process_runner import process_manager
from agents.band_orchestrator.agent_core.schema import (
    ConvertAgentInput,
    CreateBandAgentInput,
    ListGeneratedAgentsInput,
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
        cleanup_paths=[meta["folder"]],
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
        cleanup_paths=[meta["integration_path"], log_path],
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


def _custom_tools() -> list[CustomToolDef]:
    return [
        (CreateBandAgentInput, _create_band_agent),
        (ConvertAgentInput, _convert_agent),
        (ListGeneratedAgentsInput, _list_agents),
        (StopGeneratedAgentInput, _stop_agent),
        (PublishAgentInput, _publish_agent),
    ]


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
