import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
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


class DebugAttempt(Base):
    __tablename__ = "debug_attempts"

    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'diagnosing', 'patching', 'testing', 'passed', 'failed', 'stopped', 'error')",
            name="ck_debug_attempts_status",
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

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "execution_plans.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )

    parent_change_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "change_sets.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )

    new_change_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "change_sets.id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=True,
    )

    failed_execution_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "execution_runs.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )

    retry_execution_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "execution_runs.id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=True,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )

    failure_category: Mapped[str] = mapped_column(
        String(50),
        index=True,
    )

    diagnosis: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    likely_root_cause: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    diff_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    failure_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    stop_reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    input_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    output_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    total_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    latency_ms: Mapped[float | None] = mapped_column(
        Float,
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
