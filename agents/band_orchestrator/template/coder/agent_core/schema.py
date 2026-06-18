"""Pydantic models for coder tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CloneRepoInput(BaseModel):
    """Clone or update the configured repository."""


class CreateBranchInput(BaseModel):
    branch_name: str = Field(description="Git branch name for the change")


class ReadFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to repo root to read before editing")


class ListRepoFilesInput(BaseModel):
    subdir: str | None = Field(
        default=None, description="Optional subdirectory to list; defaults to repo root"
    )


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
    """Return configured repo and default branch."""


class RestoreServiceInput(BaseModel):
    """Clear demo-app chaos fault if the service is still unhealthy."""


class FetchHealthInput(BaseModel):
    """Fetch the configured hosted app health endpoint."""
