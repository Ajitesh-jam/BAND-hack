from pydantic import BaseModel, Field


class CloneRepoInput(BaseModel):
    pass


class CreateBranchInput(BaseModel):
    branch_name: str = Field(description="Git branch name for the change")


class ReadFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to repo root")


class WriteFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to repo root")
    content: str = Field(description="Full file content")


class CommitPushInput(BaseModel):
    message: str
    branch: str


class RepoInfoInput(BaseModel):
    pass
