"""Scribe agent — postmortems and memory."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import SCRIBE_PROMPT
from band.tools.memory_ops import fetch_room_context, store_incident_memory

from agents.scribe.agent_core.schema import FetchContextInput, StoreMemoryInput
logging.basicConfig(level=logging.INFO, format="%(asctime)s [scribe] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (FetchContextInput, lambda inp: fetch_room_context(inp.chat_id)),
        (StoreMemoryInput, lambda inp: store_incident_memory(inp.content, inp.incident_id)),
    ]


def build_adapter():
    return adapter_sdk(SCRIBE_PROMPT, additional_tools=_custom_tools(), enable_memory=True)


def cli() -> None:
    create_and_run(build_adapter(), "scribe", "Scribe")


if __name__ == "__main__":
    cli()
