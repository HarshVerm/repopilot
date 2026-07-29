import uuid
from datetime import datetime

from sqlalchemy import (
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


class Publication(Base):
    __tablename__ = "publications"

    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'publishing', 'local_committed', 'pushed', 'published', 'failed', 'partially_published')",
            name="ck_publications_status",
        ),
        UniqueConstraint(
            "review_id",
            name="uq_publications_review_id",
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

    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "final_reviews.id",
            ondelete="RESTRICT",
        ),
        index=True,
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

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )

    repository_owner: Mapped[str] = mapped_column(
        String(100),
    )

    repository_name: Mapped[str] = mapped_column(
        String(100),
    )

    base_branch: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    branch_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    base_commit_sha: Mapped[str] = mapped_column(
        String(64)
    )

    approved_diff_hash: Mapped[str] = mapped_column(
        String(64)
    )

    working_tree_diff_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    staged_diff_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    commit_diff_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    remote_head_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    pull_request_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    pull_request_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    remote_branch_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    pr_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    publication_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    failure_stage: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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
