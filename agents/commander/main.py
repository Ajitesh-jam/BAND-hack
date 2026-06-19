"""Commander agent for company Band workflows."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import COMMANDER_PROMPT
from band.tools import approval

from agents.commander.agent_core.schema import Request_ApprovalInput

logging.basicConfig(level=logging.INFO, format="%(asctime)s [commander] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (
            Request_ApprovalInput,
            lambda inp: approval.request_human_approval(inp.summary, inp.incident_id),
        ),
    ]


def build_adapter():
    return adapter_sdk(COMMANDER_PROMPT, additional_tools=_custom_tools(), enable_memory=True)


def cli() -> None:
    create_and_run(build_adapter(), "commander", "Commander")


if __name__ == "__main__":
    cli()
