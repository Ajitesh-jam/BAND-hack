"""GitHub agent — push and PR only, after human approval."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import GITHUB_AGENT_PROMPT
from band.tools import github_ops

from agents.github_agent.agent_core.schema import (
    CommitPushInput,
    CreateBranchInput,
    MergePRInput,
    OpenPRInput,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [github-agent] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (CreateBranchInput, lambda inp: github_ops.create_branch(inp.branch_name)),
        (CommitPushInput, lambda inp: github_ops.commit_and_push(inp.message, inp.branch)),
        (OpenPRInput, lambda inp: github_ops.open_pull_request(inp.title, inp.body, inp.branch, inp.base)),
        (MergePRInput, lambda inp: github_ops.merge_pull_request(inp.pr_url_or_number)),
    ]


def build_adapter():
    return adapter_sdk(
        GITHUB_AGENT_PROMPT,
        additional_tools=_custom_tools(),
        permission_mode="bypassPermissions",
    )


def cli() -> None:
    create_and_run(build_adapter(), "github_agent", "GitHub Agent")


if __name__ == "__main__":
    cli()
