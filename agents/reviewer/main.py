"""Reviewer agent (Codex adapter — cross-model review)."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from thenvoi.adapters import CodexAdapter, CodexAdapterConfig
from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import create_and_run
from band.prompts import REVIEWER_PROMPT
from band.tools import github_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s [reviewer] %(message)s")


class FetchPRDiffInput(BaseModel):
    pr_url_or_number: str = Field(description="GitHub PR URL or number from fix-engineer")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (FetchPRDiffInput, lambda inp: github_ops.fetch_pr_diff(inp.pr_url_or_number)),
    ]


def build_adapter() -> CodexAdapter:
    return CodexAdapter(
        config=CodexAdapterConfig(custom_section=REVIEWER_PROMPT),
        additional_tools=_custom_tools(),
    )


def cli() -> None:
    create_and_run(build_adapter(), "reviewer", "Reviewer")


if __name__ == "__main__":
    cli()
