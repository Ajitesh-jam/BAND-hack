"""Coder agent for implementing plans and opening PRs."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import CODER_PROMPT
from band.tools import demo_app, github_ops

from agents.coder.agent_core.schema import (
    CloneRepoInput,
    CommitPushInput,
    CreateBranchInput,
    FetchHealthInput,
    ListRepoFilesInput,
    MergePRInput,
    OpenPRInput,
    ReadFileInput,
    RepoInfoInput,
    RestoreServiceInput,
    WriteFileInput,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [coder] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (RepoInfoInput, lambda _: github_ops.get_repo_info()),
        (RestoreServiceInput, lambda _: demo_app.clear_chaos()),
        (FetchHealthInput, lambda _: demo_app.fetch_health()),
        (CloneRepoInput, lambda _: github_ops.clone_or_pull_repo()),
        (ListRepoFilesInput, lambda inp: github_ops.list_repo_files(inp.subdir)),
        (ReadFileInput, lambda inp: github_ops.read_file(inp.relative_path)),
        (CreateBranchInput, lambda inp: github_ops.create_branch(inp.branch_name)),
        (WriteFileInput, lambda inp: github_ops.write_file(inp.relative_path, inp.content)),
        (CommitPushInput, lambda inp: github_ops.commit_and_push(inp.message, inp.branch)),
        (OpenPRInput, lambda inp: github_ops.open_pull_request(inp.title, inp.body, inp.branch)),
        (MergePRInput, lambda inp: github_ops.merge_pull_request(inp.pr_url_or_number)),
    ]


def build_adapter():
    return adapter_sdk(
        CODER_PROMPT,
        additional_tools=_custom_tools(),
        permission_mode="bypassPermissions",
    )


def cli() -> None:
    create_and_run(build_adapter(), "coder", "Coder")


if __name__ == "__main__":
    cli()
