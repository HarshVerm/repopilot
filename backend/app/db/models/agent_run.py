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


class AgentRun(Base):
    __tablename__ = "agent_runs"

    __table_args__ = (
        CheckConstraint(
            "agent_type in ('planner', 'coder', 'debugger')",
            name="ck_agent_runs_agent_type",
        ),
        CheckConstraint(
            "status in ('started', 'completed', 'failed', 'cancelled')",
            name="ck_agent_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "repo_pilot_tasks.id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    agent_type: Mapped[str] = mapped_column(
        String(30),
        index=True,
    )
    model: Mapped[str] = mapped_column(
        String(100),
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="started",
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    latency_ms: Mapped[float | None] = mapped_column(
        Float,
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
    tool_calls_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    error_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "execution_plans.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    change_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "change_sets.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    debug_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "debug_attempts.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    request_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(100),
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
