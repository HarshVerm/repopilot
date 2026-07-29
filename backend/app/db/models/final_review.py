import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import (
    JSONB,
    UUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.base import Base


class FinalReview(Base):
    __tablename__ = "final_reviews"

    __table_args__ = (
        CheckConstraint(
            "status in ('pending_review', 'approved', 'rejected', "
            "'changes_requested', 'superseded')",
            name="ck_final_reviews_status",
        ),
        CheckConstraint(
            "decision is null or decision in "
            "('approved', 'rejected', 'changes_requested')",
            name="ck_final_reviews_decision",
        ),
        Index(
            "ux_final_reviews_active_exact_diff",
            "change_set_id",
            "diff_hash",
            "base_commit_sha",
            unique=True,
            postgresql_where=text(
                "status in ('pending_review', 'approved')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        index=True,
    )

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "repo_pilot_tasks.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    review_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "execution_plans.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )

    change_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "change_sets.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )

    execution_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "execution_runs.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending_review",
        index=True,
    )

    base_commit_sha: Mapped[str] = mapped_column(
        String(64)
    )

    diff_hash: Mapped[str] = mapped_column(
        String(64),
        index=True,
    )

    files_changed: Mapped[int] = mapped_column(
        Integer
    )

    lines_added: Mapped[int] = mapped_column(
        Integer
    )

    lines_deleted: Mapped[int] = mapped_column(
        Integer
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    risk_summary: Mapped[str] = mapped_column(
        Text
    )

    decision: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    reviewed_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    files_json: Mapped[list] = mapped_column(
        JSONB
    )

    verification_json: Mapped[dict] = mapped_column(
        JSONB
    )

    debug_history_json: Mapped[dict] = mapped_column(
        JSONB
    )

    issue_json: Mapped[dict] = mapped_column(
        JSONB
    )

    plan_snapshot_json: Mapped[dict] = mapped_column(
        JSONB
    )

    diff: Mapped[str] = mapped_column(
        Text
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
