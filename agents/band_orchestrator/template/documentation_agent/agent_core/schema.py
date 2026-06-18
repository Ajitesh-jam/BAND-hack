"""Pydantic input models for documentation-agent tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryContextInput(BaseModel):
    """Retrieve graph context and relevant doc chunks for a query."""

    query: str = Field(..., description="Question about architecture, dependencies, docs, or changes.")


class GetGraphOverviewInput(BaseModel):
    """Return the codebase dependency graph overview."""


class GetFileDependenciesInput(BaseModel):
    """Show import/impact dependencies for a specific file."""

    file_path: str = Field(..., description="Relative file path in the codebase graph.")


class GetCommitHistoryInput(BaseModel):
    """Return recent commit-history context and file co-change edges."""

    query: str | None = Field(
        default=None,
        description="Optional search query over commit subjects and changed files.",
    )
    limit: int = Field(default=10, description="Maximum commits to return.")


class UpdateGraphInput(BaseModel):
    """Rebuild graph, docs RAG, and commit-history artifacts."""

    github_url: str | None = Field(
        default=None,
        description="Optional GitHub repo URL. If omitted, the configured company repo is used.",
    )
