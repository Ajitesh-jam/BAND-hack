"""Planner agent for feature and incident plans."""

from __future__ import annotations

import logging

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import PLANNER_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [planner] %(message)s")


def build_adapter():
    return adapter_sdk(PLANNER_PROMPT, enable_memory=True)


def cli() -> None:
    create_and_run(build_adapter(), "planner", "Planner")


if __name__ == "__main__":
    cli()
