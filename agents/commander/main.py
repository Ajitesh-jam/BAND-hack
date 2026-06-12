"""Incident Commander agent (Claude Code CLI — no Anthropic API credits)."""

from __future__ import annotations

import logging

from band.agents.base import create_and_run
from band.agents.base import adapter_sdk
from band.prompts import COMMANDER_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [commander] %(message)s")


def build_adapter():
    return adapter_sdk(COMMANDER_PROMPT, enable_memory=True)


def cli() -> None:
    create_and_run(build_adapter(), "incident_commander", "Incident Commander")


if __name__ == "__main__":
    cli()

