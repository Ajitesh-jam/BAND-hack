"""Pydantic models for commander tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RequestApprovalInput(BaseModel):
    """Notify the human and open a one-click Approve/Reject page for the current room."""

    summary: str = Field(
        description="Short human-readable summary of the reviewed change and its critical points"
    )
    incident_id: str = Field(
        default="", description="Incident or feature id, e.g. INC-0618-001"
    )
