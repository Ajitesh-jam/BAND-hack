"""Fix Engineer agent (configurable SDK adapter)."""

from __future__ import annotations

import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import adapter_sdk, create_and_run
from band.prompts import FIX_ENGINEER_PROMPT
from band.tools import demo_app, github_ops

from agents.fix_engineer.agent_core.schema import CloneRepoInput, CreateBranchInput, WriteFileInput, CommitPushInput, OpenPRInput, MergePRInput, RepoInfoInput, RestoreServiceInput, FetchHealthInput

logging.basicConfig(level=logging.INFO, format="%(asctime)s [fix-engineer] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (RepoInfoInput, lambda _: github_ops.get_repo_info()),
        (RestoreServiceInput, lambda _: demo_app.clear_chaos()),
        (FetchHealthInput, lambda _: demo_app.fetch_health()),
        (CloneRepoInput, lambda _: github_ops.clone_or_pull_repo()),
        (CreateBranchInput, lambda inp: github_ops.create_branch(inp.branch_name)),
        (WriteFileInput, lambda inp: github_ops.write_file(inp.relative_path, inp.content)),
        (CommitPushInput, lambda inp: github_ops.commit_and_push(inp.message, inp.branch)),
        (OpenPRInput, lambda inp: github_ops.open_pull_request(inp.title, inp.body, inp.branch)),
        (MergePRInput, lambda inp: github_ops.merge_pull_request(inp.pr_url_or_number)),
    ]


def build_adapter():
    # bypassPermissions: gh/git run via custom tools + subprocess, not blocked Bash prompts
    return adapter_sdk(
        FIX_ENGINEER_PROMPT,
        additional_tools=_custom_tools(),
        permission_mode="bypassPermissions",
    )


def cli() -> None:
    create_and_run(build_adapter(), "fix_engineer", "Fix Engineer")


if __name__ == "__main__":
    cli()
