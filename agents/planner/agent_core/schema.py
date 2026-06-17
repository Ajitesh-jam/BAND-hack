from pydantic import BaseModel, Field


class EmitPlanInput(BaseModel):
    plan: str = Field(..., description="Structured implementation plan (markdown).")
    files: list[str] = Field(default_factory=list, description="Files to touch.")


class RequestSubPlannersInput(BaseModel):
    partitions: list[str] = Field(
        ...,
        description="Two partition descriptions for planner_alpha and planner_beta.",
    )
