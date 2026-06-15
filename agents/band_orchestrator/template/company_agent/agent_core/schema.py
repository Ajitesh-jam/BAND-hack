"""Pydantic input models for company code-context agent tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryContextInput(BaseModel):
    """Retrieve graph context and relevant doc chunks for a query."""

    query: str = Field(..., description="Question about architecture, dependencies, or internal docs.")


class GetGraphOverviewInput(BaseModel):
    """Return the full codebase dependency graph overview."""


class GetFileDependenciesInput(BaseModel):
    """Show import/impact dependencies for a specific file."""

    file_path: str = Field(..., description="Relative file path in the codebase graph.")
