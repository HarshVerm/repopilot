# Module purpose: Define validated publishing API payload schemas.

from pydantic import BaseModel


# Purpose: Validate and represent publication response data.
class PublicationResponse(BaseModel):
    publication_id: str
    review_id: str
    workspace_id: str
    plan_id: str
    change_set_id: str
    status: str
    repository: dict
    base_branch: str | None
    head_branch: str | None
    base_commit_sha: str
    approved_diff_hash: str
    working_tree_diff_hash: str | None = None
    staged_diff_hash: str | None = None
    commit_diff_hash: str | None = None
    commit_sha: str | None = None
    remote_head_sha: str | None = None
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    pull_request_author_login: str | None = None
    retry_count: int
    error_message: str | None = None
    failure_stage: str | None = None
    failure_reason: str | None = None
    created_at: str | None
    updated_at: str | None
    remote_branch_created_at: str | None = None
    pr_created_at: str | None = None
    published_at: str | None = None
