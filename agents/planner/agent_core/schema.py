"""Read-only repo + hosted demo app log tools for planner."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepoInfoInput(BaseModel):
    """Return configured repo URL and default branch."""


class CloneRepoInput(BaseModel):
    """Clone or pull the shared repository into .workspace/repo."""


class ReadFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to repo root")


class ListRepoFilesInput(BaseModel):
    subdir: str | None = Field(default=None, description="Optional subdirectory to list")


class FetchHealthInput(BaseModel):
    """Fetch hosted demo app health snapshot."""


class FetchLogsInput(BaseModel):
    limit: int = Field(default=50, description="Max activity log entries")
    level: str | None = Field(default=None, description="Optional filter: info, warn, error")


class FetchDeploymentLogsInput(BaseModel):
    limit: int = Field(default=30, description="Max deployment log entries")
