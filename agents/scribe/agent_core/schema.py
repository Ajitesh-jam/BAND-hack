from pydantic import BaseModel, Field

class FetchContextInput(BaseModel):
    chat_id: str = Field(description="Incident room chat ID")


class StoreMemoryInput(BaseModel):
    content: str = Field(description="Postmortem summary to persist")
    incident_id: str = Field(description="Incident ID e.g. INC-0612-001")