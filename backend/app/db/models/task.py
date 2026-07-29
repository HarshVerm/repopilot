import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import (
    UUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.base import Base


TASK_STATUSES = (
    "created",
    "repository_preparing",
    "repository_ready",
    "indexing",
    "indexed",
    "retrieving",
    "planning",
    "plan_pending_approval",
    "plan_approved",
    "plan_rejected",
    "coding",
    "patch_generated",
    "testing",
    "test_failed",
    "debugging",
    "verification_passed",
    "review_pending",
    "review_approved",
    "review_rejected",
    "publishing",
    "completed",
    "failed",
    "cancelled",
)


class RepoPilotTask(Base):
    __tablename__ = "repo_pilot_tasks"

    __table_args__ = (
        CheckConstraint(
            "status in "
            + str(TASK_STATUSES).replace('"', "'"),
            name="ck_repo_pilot_tasks_status",
        ),
        UniqueConstraint(
            "repository_owner",
            "repository_name",
            "issue_number",
            "completed_at",
            name="uq_repo_pilot_tasks_issue_completed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    repository_owner: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )
    repository_name: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )
    issue_number: Mapped[int] = mapped_column(
        Integer,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(40),
        default="created",
        index=True,
    )
    current_step: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    last_error_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    failure_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    retryable: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    active_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "execution_plans.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    active_change_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "change_sets.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    active_execution_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "execution_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    active_review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "final_reviews.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "publications.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class TaskOperationLock(Base):
    __tablename__ = "task_operation_locks"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "repo_pilot_tasks.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    operation: Mapped[str] = mapped_column(
        String(100),
    )
    owner: Mapped[str] = mapped_column(
        String(100),
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
