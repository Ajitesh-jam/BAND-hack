from pydantic import BaseModel, Field


class BuildContextInput(BaseModel):
    target_path: str | None = Field(
        default=None,
        description="Path to codebase root (default: repo demo-app/).",
    )


class QueryContextInput(BaseModel):
    question: str = Field(..., description="Question to answer from docs RAG and graphify.")


class GraphOverviewInput(BaseModel):
    target_path: str | None = Field(default=None, description="Codebase root for graphify-out.")


class FileDependenciesInput(BaseModel):
    relative_path: str = Field(..., description="File path relative to demo-app root.")
    target_path: str | None = Field(default=None, description="Codebase root.")
