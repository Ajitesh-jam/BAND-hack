"""Pydantic input models for the Band Orchestrator's custom tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterAgentInput(BaseModel):
    """Register a Band agent and write credentials to agent_config.yaml."""

    role: str = Field(
        ...,
        description="Config key: company_agent, watchdog, planner, coder, reviewer, merger, etc.",
    )
    force: bool = Field(
        default=False,
        description="Re-register on Band even if an entry exists (uses a new Band slot).",
    )


class RegisterTeamInput(BaseModel):
    """Register all team agents missing from agent_config.yaml (orchestrator authority)."""

    force: bool = Field(default=False, description="Force re-register every team agent on Band.")


class DeployAgentInput(BaseModel):
    """Deploy a team agent subprocess (orchestrator-owned — no double-spawn)."""

    role: str = Field(
        ...,
        description=(
            "Agent role: company_agent, watchdog, planner, planner_alpha, planner_beta, "
            "coder, reviewer, merger."
        ),
    )
    partition: str | None = Field(
        default=None,
        description="Partition scope for planner_alpha/planner_beta.",
    )


class ListAgentsInput(BaseModel):
    """List agents currently deployed by the orchestrator."""


class StopAgentInput(BaseModel):
    """Stop a deployed agent subprocess by role name."""

    name: str = Field(..., description="Role name (e.g. planner, coder).")


class BuildContextInput(BaseModel):
    """Rebuild graphify graph + docs RAG (deterministic, no LLM)."""

    target_path: str | None = Field(default=None, description="Codebase root (default demo-app/).")


class GetContextPathsInput(BaseModel):
    """Return graph/docs paths to hand off to the planner."""

    target_path: str | None = Field(default=None, description="Codebase root.")
