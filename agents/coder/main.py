"""Coder agent — implements planner output via local git edits."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from agents.coder.agent_core.schema import (
    CloneRepoInput,
    CommitPushInput,
    CreateBranchInput,
    ReadFileInput,
    RepoInfoInput,
    WriteFileInput,
)
from band.agents.base import adapter_sdk, create_and_run
from band.config import get_settings
from band.prompts import CODER_PROMPT
from band.tools import github_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s [coder] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (RepoInfoInput, lambda _: github_ops.get_repo_info()),
        (CloneRepoInput, lambda _: github_ops.clone_or_pull_repo()),
        (CreateBranchInput, lambda inp: github_ops.create_branch(inp.branch_name)),
        (ReadFileInput, lambda inp: github_ops.read_file(inp.relative_path)),
        (WriteFileInput, lambda inp: github_ops.write_file(inp.relative_path, inp.content)),
        (CommitPushInput, lambda inp: github_ops.commit_and_push(inp.message, inp.branch)),
    ]


def build_adapter():
    settings = get_settings()
    return adapter_sdk(
        CODER_PROMPT,
        adapter_type=settings.coder_adapter,
        model=settings.coder_model,
        additional_tools=_custom_tools(),
        permission_mode="bypassPermissions",
    )


def cli() -> None:
    create_and_run(build_adapter(), "coder", "Coder")


if __name__ == "__main__":
    cli()
