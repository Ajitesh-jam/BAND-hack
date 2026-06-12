"""Fix Engineer agent (Claude SDK adapter)."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import create_and_run
from band.agents.claude_sdk import claude_agent
from band.prompts import FIX_ENGINEER_PROMPT
from band.tools import demo_app, github_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s [fix-engineer] %(message)s")


class CloneRepoInput(BaseModel):
    pass


class CreateBranchInput(BaseModel):
    branch_name: str = Field(description="Git branch name for the fix")


class WriteFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to repo root")
    content: str = Field(description="Full file content")


class CommitPushInput(BaseModel):
    message: str
    branch: str


class OpenPRInput(BaseModel):
    title: str
    body: str
    branch: str


class MergePRInput(BaseModel):
    pr_url_or_number: str = Field(description="PR URL or number after human approval")


class RepoInfoInput(BaseModel):
    pass


class RestoreServiceInput(BaseModel):
    pass


class FetchHealthInput(BaseModel):
    pass


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
    return claude_agent(
        FIX_ENGINEER_PROMPT,
        additional_tools=_custom_tools(),
        permission_mode="bypassPermissions",
    )


def cli() -> None:
    create_and_run(build_adapter(), "fix_engineer", "Fix Engineer")


if __name__ == "__main__":
    cli()
