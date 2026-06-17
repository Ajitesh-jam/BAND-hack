"""Merger agent — merges approved PRs and clears chaos."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from agents.merger.agent_core.schema import MergePRInput
from band.agents.base import adapter_sdk, create_and_run
from band.prompts import MERGER_PROMPT
from band.tools import github_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s [merger] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (MergePRInput, lambda inp: github_ops.merge_pull_request(inp.pr_url_or_number)),
    ]


def build_adapter():
    settings = get_settings()
    return adapter_sdk(
        MERGER_PROMPT,
        adapter_type=settings.merger_adapter,
        model=settings.merger_model,
        additional_tools=_custom_tools(),
        permission_mode="bypassPermissions",
    )


def cli() -> None:
    create_and_run(build_adapter(), "merger", "Merger")


if __name__ == "__main__":
    cli()
