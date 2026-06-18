"""Pydantic models for reviewer tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FetchPRDiffInput(BaseModel):
    pr_url_or_number: str = Field(description="PR URL or number to diff")
