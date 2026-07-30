# Module purpose: Define persistent task database models.

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    "plan_revision_required",
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


# Purpose: Persist repo pilot task records.
class RepoPilotTask(Base):
    __tablename__ = "repo_pilot_tasks"

    __table_args__ = (
        CheckConstraint(
            "status in "
            + str(TASK_STATUSES).replace('"', "'"),
            name="ck_repo_pilot_tasks_status",
        ),
        CheckConstraint(
            "autonomy_mode in ('standard', 'strict')",
            name="ck_repo_pilot_tasks_autonomy_mode",
        ),
        Index(
            "ux_repo_pilot_tasks_native_active_issue",
            "user_id",
            "repository_id",
            "issue_number",
            unique=True,
            postgresql_where=text(
                "user_id is not null and repository_id is not null and "
                "status not in ('completed', 'plan_rejected', "
                "'review_rejected', 'failed', 'cancelled')"
            ),
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )
    installation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "github_installations.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "repositories.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
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
    github_issue_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    issue_title: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )
    issue_body_snapshot: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    issue_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    issue_author: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    issue_labels: Mapped[list] = mapped_column(
        JSONB,
        default=list,
    )
    issue_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    issue_updated_at_at_creation: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    issue_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    user_instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    base_branch: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    base_commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    autonomy_mode: Mapped[str] = mapped_column(
        String(20),
        default="strict",
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
    cancelled_at: Mapped[datetime | None] = mapped_column(
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


# Purpose: Persist task operation lock records.
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
