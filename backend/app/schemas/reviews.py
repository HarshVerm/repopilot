# Module purpose: Define validated reviews API payload schemas.

from pydantic import (
    BaseModel,
    Field,
)
from uuid import UUID


# Purpose: Validate and represent reject review request data.
class RejectReviewRequest(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=4000,
    )


# Purpose: Validate and represent task review action request data.
class TaskReviewActionRequest(BaseModel):
    review_id: UUID
    changeset_id: UUID
    diff_hash: str = Field(
        min_length=64,
        max_length=64,
    )


# Purpose: Represent the request changes request API data.
class RequestChangesRequest(TaskReviewActionRequest):
    feedback: str = Field(
        min_length=1,
        max_length=10_000,
    )


# Purpose: Represent the reject task review request API data.
class RejectTaskReviewRequest(TaskReviewActionRequest):
    reason: str | None = Field(
        default=None,
        max_length=10_000,
    )


# Purpose: Validate and represent review decision response data.
class ReviewDecisionResponse(BaseModel):
    review_id: str
    status: str
    decision: str | None
    reviewed_at: str | None
    rejection_reason: str | None = None
    feedback: str | None = None


# Purpose: Validate and represent final review response data.
class FinalReviewResponse(BaseModel):
    review_id: str
    status: str
    review_version: int = 1
    issue: dict
    plan: dict
    changes: dict
    verification: dict
    debug_history: dict
    risk_summary: str
    base_commit_sha: str
    diff_hash: str
    diff: str
    diff_truncated: bool = False
    full_diff_available: bool = True
    created_at: str | None
    reviewed_at: str | None
    decision: str | None = None
    rejection_reason: str | None = None
    feedback: str | None = None
