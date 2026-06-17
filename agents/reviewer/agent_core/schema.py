from pydantic import BaseModel, Field


class FetchPRDiffInput(BaseModel):
    pr_url_or_number: str = Field(description="GitHub PR URL or number from fix-engineer")