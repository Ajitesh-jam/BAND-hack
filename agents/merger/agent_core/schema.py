from pydantic import BaseModel, Field


class MergePRInput(BaseModel):
    pr_url_or_number: str = Field(..., description="PR URL or number after human approval.")
