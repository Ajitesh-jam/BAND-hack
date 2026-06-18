"""Reviewer agent for bounded PR review."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import REVIEWER_PROMPT
from band.tools import demo_app, github_ops

from agents.reviewer.agent_core.schema import (
    FetchDeploymentLogsInput,
    FetchHealthInput,
    FetchLogsInput,
    FetchPRDiffInput,
    ListRepoFilesInput,
    ReadFileInput,
    RecoverServiceInput,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [reviewer] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (FetchPRDiffInput, lambda inp: github_ops.fetch_pr_diff(inp.pr_url_or_number)),
        (ListRepoFilesInput, lambda inp: github_ops.list_repo_files(inp.subdir)),
        (ReadFileInput, lambda inp: github_ops.read_file(inp.relative_path)),
        (FetchHealthInput, lambda _: demo_app.fetch_health()),
        (FetchLogsInput, lambda inp: demo_app.fetch_logs(inp.limit)),
        (FetchDeploymentLogsInput, lambda inp: demo_app.fetch_deployment_logs(inp.limit)),
        (RecoverServiceInput, lambda _: demo_app.recover_service()),
    ]


def build_adapter():
    return adapter_sdk(REVIEWER_PROMPT, additional_tools=_custom_tools())


def cli() -> None:
    create_and_run(build_adapter(), "reviewer", "Reviewer")


if __name__ == "__main__":
    cli()
