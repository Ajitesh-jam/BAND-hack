"""GitHub agent — push/PR only (after human approval)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateBranchInput(BaseModel):
    branch_name: str = Field(description="Branch to create/checkout before push")


class CommitPushInput(BaseModel):
    message: str = Field(description="Commit message")
    branch: str = Field(description="Branch to commit on and push to origin")


class OpenPRInput(BaseModel):
    title: str
    body: str
    branch: str
    base: str | None = Field(default=None, description="Target base branch")


class MergePRInput(BaseModel):
    pr_url_or_number: str = Field(description="PR URL or number to merge after human approval")
