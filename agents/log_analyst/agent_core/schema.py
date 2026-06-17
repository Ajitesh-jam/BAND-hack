from pydantic import BaseModel, Field

class FetchLogsInput(BaseModel):
    limit: int = Field(default=100, description="Max log lines")
    level: str | None = Field(default=None, description="Filter by level e.g. ERROR")


class FetchMetricsInput(BaseModel):
    pass


class FetchChaosStatusInput(BaseModel):
    pass

    
class FetchHealthInput(BaseModel):
    pass