"""Reviewer agent (configurable SDK adapter — cross-model review)."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import REVIEWER_PROMPT
from band.tools import github_ops

from agents.reviewer.agent_core.schema import FetchPRDiffInput

logging.basicConfig(level=logging.INFO, format="%(asctime)s [reviewer] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (FetchPRDiffInput, lambda inp: github_ops.fetch_pr_diff(inp.pr_url_or_number)),
    ]


def build_adapter():
    return adapter_sdk(REVIEWER_PROMPT, additional_tools=_custom_tools())


def cli() -> None:
    create_and_run(build_adapter(), "reviewer", "Reviewer")


if __name__ == "__main__":
    cli()
