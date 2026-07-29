import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
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


class ExecutionRun(Base):
    __tablename__ = "execution_runs"

    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'running', 'passed', 'failed', 'timeout', 'error')",
            name="ck_execution_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    change_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "change_sets.id",
            ondelete="RESTRICT",
        ),
        index=True,
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

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    duration_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    commands_json: Mapped[list] = mapped_column(
        JSONB
    )

    results_json: Mapped[list] = mapped_column(
        JSONB
    )

    tests_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    lint_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    typecheck_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    build_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    timed_out: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    sandbox_runtime: Mapped[str] = mapped_column(
        String(50),
        default="docker",
    )

    runtime_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
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
