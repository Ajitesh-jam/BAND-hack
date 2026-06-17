"""Reviewer agent — Codex cross-model review and PR creation."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from agents.reviewer.agent_core.schema import BranchDiffInput, OpenPRInput
from band.agents.base import adapter_sdk, create_and_run
from band.config import get_settings
from band.prompts import REVIEWER_PROMPT
from band.tools import github_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s [reviewer] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (BranchDiffInput, lambda inp: github_ops.get_branch_diff(inp.branch, inp.base)),
        (
            OpenPRInput,
            lambda inp: github_ops.open_pull_request(inp.title, inp.body, inp.branch, inp.base),
        ),
    ]


def build_adapter():
    settings = get_settings()
    return adapter_sdk(
        REVIEWER_PROMPT,
        adapter_type=settings.reviewer_adapter,
        model=settings.reviewer_model,
        additional_tools=_custom_tools(),
    )


def cli() -> None:
    create_and_run(build_adapter(), "reviewer", "Reviewer")


if __name__ == "__main__":
    cli()
