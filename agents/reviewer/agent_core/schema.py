from pydantic import BaseModel, Field


class BranchDiffInput(BaseModel):
    branch: str = Field(..., description="Branch name to review.")
    base: str | None = Field(default=None, description="Base branch (default: repo default).")


class OpenPRInput(BaseModel):
    title: str
    body: str
    branch: str
    base: str | None = Field(default=None, description="Base branch for the PR.")
