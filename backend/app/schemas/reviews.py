from pydantic import (
    BaseModel,
    Field,
)


class RejectReviewRequest(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=4000,
    )


class ReviewDecisionResponse(BaseModel):
    review_id: str
    status: str
    decision: str | None
    reviewed_at: str | None
    rejection_reason: str | None = None


class FinalReviewResponse(BaseModel):
    review_id: str
    status: str
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
