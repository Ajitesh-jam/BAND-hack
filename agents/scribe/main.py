"""Scribe agent (Claude Code CLI) — postmortems and memory."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import create_and_run
from band.agents.claude_sdk import claude_agent
from band.prompts import SCRIBE_PROMPT
from band.tools.memory_ops import fetch_room_context, store_incident_memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [scribe] %(message)s")


class FetchContextInput(BaseModel):
    chat_id: str = Field(description="Incident room chat ID")


class StoreMemoryInput(BaseModel):
    content: str = Field(description="Postmortem summary to persist")
    incident_id: str = Field(description="Incident ID e.g. INC-0612-001")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (FetchContextInput, lambda inp: fetch_room_context(inp.chat_id)),
        (StoreMemoryInput, lambda inp: store_incident_memory(inp.content, inp.incident_id)),
    ]


def build_adapter():
    return claude_agent(SCRIBE_PROMPT, additional_tools=_custom_tools(), enable_memory=True)


def cli() -> None:
    create_and_run(build_adapter(), "scribe", "Scribe")


if __name__ == "__main__":
    cli()
