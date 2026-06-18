"""Coder agent — implements fixes locally; push/PR happens via github_agent after approval."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import CODER_PROMPT
from band.tools import demo_app, github_ops

from agents.coder.agent_core.schema import (
    CloneRepoInput,
    CreateBranchInput,
    FetchDeploymentLogsInput,
    FetchHealthInput,
    FetchLogsInput,
    InjectFatalErrorInput,
    ListRepoFilesInput,
    ReadFileInput,
    RepoInfoInput,
    RestoreServiceInput,
    WriteFileInput,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [coder] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (RepoInfoInput, lambda _: github_ops.get_repo_info()),
        (CloneRepoInput, lambda _: github_ops.clone_or_pull_repo()),
        (CreateBranchInput, lambda inp: github_ops.create_branch(inp.branch_name)),
        (ListRepoFilesInput, lambda inp: github_ops.list_repo_files(inp.subdir)),
        (ReadFileInput, lambda inp: github_ops.read_file(inp.relative_path)),
        (WriteFileInput, lambda inp: github_ops.write_file(inp.relative_path, inp.content)),
        (RestoreServiceInput, lambda _: demo_app.recover_service()),
        (FetchHealthInput, lambda _: demo_app.fetch_health()),
        (FetchLogsInput, lambda inp: demo_app.fetch_logs(inp.limit, inp.level)),
        (FetchDeploymentLogsInput, lambda inp: demo_app.fetch_deployment_logs(inp.limit)),
        (InjectFatalErrorInput, lambda _: demo_app.trigger_fatal_crash()),
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
