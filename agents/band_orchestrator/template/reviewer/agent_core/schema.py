"""Pydantic models for reviewer tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FetchPRDiffInput(BaseModel):
    pr_url_or_number: str = Field(
        default="local",
        description="Use 'local' for uncommitted/coder changes in the workspace clone",
    )


class FetchHealthInput(BaseModel):
    """Fetch hosted demo app /api/health.json to verify recovery."""


class FetchLogsInput(BaseModel):
    limit: int = Field(default=50, description="Max activity log entries")


class FetchDeploymentLogsInput(BaseModel):
    limit: int = Field(default=30, description="Max deployment log entries")


class RecoverServiceInput(BaseModel):
    """Recover hosted demo app if health is still failing after coder's fix attempt."""


class ReadFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to .workspace/repo root")


class ListRepoFilesInput(BaseModel):
    subdir: str | None = Field(default=None, description="Optional subdirectory under .workspace/repo")
