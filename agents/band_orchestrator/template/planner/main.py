"""Planner agent — plans using documentation context and read-only repo tools."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import PLANNER_PROMPT
from band.tools import demo_app, github_ops

from agents.planner.agent_core.schema import (
    CloneRepoInput,
    FetchDeploymentLogsInput,
    FetchHealthInput,
    FetchLogsInput,
    ListRepoFilesInput,
    ReadFileInput,
    RepoInfoInput,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [planner] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (RepoInfoInput, lambda _: github_ops.get_repo_info()),
        (CloneRepoInput, lambda _: github_ops.clone_or_pull_repo()),
        (ListRepoFilesInput, lambda inp: github_ops.list_repo_files(inp.subdir)),
        (ReadFileInput, lambda inp: github_ops.read_file(inp.relative_path)),
        (FetchHealthInput, lambda _: demo_app.fetch_health()),
        (FetchLogsInput, lambda inp: demo_app.fetch_logs(inp.limit, inp.level)),
        (FetchDeploymentLogsInput, lambda inp: demo_app.fetch_deployment_logs(inp.limit)),
    ]


def build_adapter():
    return adapter_sdk(PLANNER_PROMPT, additional_tools=_custom_tools(), enable_memory=True)


def cli() -> None:
    create_and_run(build_adapter(), "planner", "Planner")


if __name__ == "__main__":
    cli()
