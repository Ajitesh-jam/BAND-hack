"""Pydantic input models for the Band Orchestrator's custom tools.

Tool names are derived from the class name with the ``Input`` suffix removed and
lowercased (e.g. ``CreateBandAgentInput`` -> ``createbandagent``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateBandAgentInput(BaseModel):
    """Create a brand-new Band agent from a description and deploy it."""

    description: str = Field(
        ..., description="What the new agent should do — its role and capabilities."
    )
    agent_id: str = Field(..., description="Band agent UUID for the NEW agent (from Band dashboard).")
    api_key: str = Field(..., description="Band API key for the NEW agent (from Band dashboard).")
    name: str | None = Field(
        default=None, description="Optional short name/slug for the new agent."
    )


class ConvertAgentInput(BaseModel):
    """Convert an existing agent codebase at a path into a Band agent and deploy it."""

    folder_path: str = Field(..., description="Absolute path to the user's existing agent folder.")
    agent_id: str = Field(..., description="Band agent UUID to assign to the converted agent.")
    api_key: str = Field(..., description="Band API key to assign to the converted agent.")


class ListGeneratedAgentsInput(BaseModel):
    """List the agents currently deployed by the orchestrator (name, pid, running)."""


class StopGeneratedAgentInput(BaseModel):
    """Stop a deployed agent by name and clean up its generated files."""

    name: str = Field(..., description="Name of the deployed agent to stop.")


class PublishAgentInput(BaseModel):
    """Open a GitHub pull request that adds a generated agent's code to the repo."""

    name: str = Field(..., description="Name of the deployed/generated agent to publish.")
    title: str | None = Field(default=None, description="Optional PR title.")
    body: str | None = Field(default=None, description="Optional PR body/description.")


class CreateCompanyContextAgentInput(BaseModel):
    """Scaffold a company code-context agent from template."""

    agent_id: str = Field(..., description="Band agent UUID for the NEW company context agent.")
    api_key: str = Field(..., description="Band API key for the NEW company context agent.")
    name: str | None = Field(
        default=None,
        description="Optional short name/slug (defaults to company_context).",
    )


class BuildCompanyContextInput(BaseModel):
    """Build graph RAG and docs RAG indexes for a scaffolded company context agent."""

    name: str = Field(..., description="Folder name of the scaffolded company context agent.")
    github_url: str | None = Field(
        default=None,
        description="Optional public GitHub repository URL to analyze for dependency graph.",
    )


class DeployCompanyContextAgentInput(BaseModel):
    """Deploy (spawn) a built company context agent process."""

    name: str = Field(..., description="Folder name of the company context agent to deploy.")


class MakeCompanyAgentsInput(BaseModel):
    """Create/build/deploy the standard company Band agent roster."""

    github_url: str = Field(..., description="Company code GitHub repository URL.")
    hosted_link: str = Field(..., description="Hosted app base URL watched by watchdog.")
    github_token: str | None = Field(
        default=None,
        description="Optional GitHub token for pushing branches and opening PRs.",
    )
