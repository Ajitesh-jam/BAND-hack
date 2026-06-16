from pydantic import BaseModel, Field

class CloneRepoInput(BaseModel):
    pass


class CreateBranchInput(BaseModel):
    branch_name: str = Field(description="Git branch name for the fix")


class WriteFileInput(BaseModel):
    relative_path: str = Field(description="Path relative to repo root")
    content: str = Field(description="Full file content")


class CommitPushInput(BaseModel):
    message: str
    branch: str


class OpenPRInput(BaseModel):
    title: str
    body: str
    branch: str


class MergePRInput(BaseModel):
    pr_url_or_number: str = Field(description="PR URL or number after human approval")


class RepoInfoInput(BaseModel):
    pass


class RestoreServiceInput(BaseModel):
    pass


class FetchHealthInput(BaseModel):
    pass


class FetchPRReviewStatusInput(BaseModel):
    pr_url_or_number: str = Field(description="PR URL or PR number to check review status on GitHub")