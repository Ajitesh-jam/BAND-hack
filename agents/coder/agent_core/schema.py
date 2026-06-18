"""Coder tools — local repo edits + hosted demo app health/logs/recover."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepoInfoInput(BaseModel):
    """Return configured repo URL and default branch."""


class CloneRepoInput(BaseModel):
    """Clone or pull the shared repository into .workspace/repo."""


class CreateBranchInput(BaseModel):
    branch_name: str = Field(description="Local git branch for the fix (not pushed until approval)")


class ReadFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to repo root to read before editing")


class ListRepoFilesInput(BaseModel):
    subdir: str | None = Field(default=None, description="Optional subdirectory to list")


class WriteFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to repo root")
    content: str = Field(description="Full file content")


class RestoreServiceInput(BaseModel):
    """Recover the hosted demo app after FATAL_APP_CRASH / inject-error (calls recover API)."""


class FetchHealthInput(BaseModel):
    """Fetch the hosted demo app /api/health.json endpoint."""


class FetchLogsInput(BaseModel):
    limit: int = Field(default=50, description="Max log entries to return")
    level: str | None = Field(default=None, description="Optional filter: info, warn, error")


class FetchDeploymentLogsInput(BaseModel):
    limit: int = Field(default=30, description="Max deployment log entries")


class InjectFatalErrorInput(BaseModel):
    """Inject a server-detectable fatal crash for incident testing (patches gh-pages health)."""
