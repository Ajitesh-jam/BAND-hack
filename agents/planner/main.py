"""Planner agent — produces structured plans; may request alpha/beta sub-planners."""

from __future__ import annotations

import json
import logging
import os

from thenvoi.runtime.custom_tools import CustomToolDef

from agents.planner.agent_core.schema import EmitPlanInput, RequestSubPlannersInput
from band.agents.base import adapter_sdk, create_and_run
from band.config import get_settings
from band.prompts import PLANNER_ALPHA_PROMPT, PLANNER_BETA_PROMPT, PLANNER_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [planner] %(message)s")


def _emit_plan(inp: EmitPlanInput) -> str:
    return json.dumps({"status": "plan_emitted", "plan": inp.plan, "files": inp.files})


def _request_sub_planners(inp: RequestSubPlannersInput) -> str:
    return json.dumps(
        {
            "status": "sub_planners_requested",
            "partitions": inp.partitions,
            "next_step": "Orchestrator should deploy planner_alpha and planner_beta.",
        }
    )


def _custom_tools() -> list[CustomToolDef]:
    return [
        (EmitPlanInput, _emit_plan),
        (RequestSubPlannersInput, _request_sub_planners),
    ]


def _prompt_for_role(config_key: str) -> str:
    if config_key == "planner_alpha":
        partition = os.environ.get("BAND_PLANNER_PARTITION", "your assigned partition")
        return PLANNER_ALPHA_PROMPT.format(partition=partition)
    if config_key == "planner_beta":
        partition = os.environ.get("BAND_PLANNER_PARTITION", "your assigned partition")
        return PLANNER_BETA_PROMPT.format(partition=partition)
    return PLANNER_PROMPT


def build_adapter(config_key: str = "planner"):
    settings = get_settings()
    return adapter_sdk(
        _prompt_for_role(config_key),
        adapter_type=settings.planner_adapter,
        model=settings.planner_model,
        additional_tools=_custom_tools(),
        enable_memory=True,
    )


def cli() -> None:
    config_key = os.environ.get("BAND_CONFIG_KEY", "planner")
    label = config_key.replace("_", " ").title()
    create_and_run(build_adapter(config_key), config_key, label)


if __name__ == "__main__":
    cli()
