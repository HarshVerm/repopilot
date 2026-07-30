# Module purpose: Define persistent execution plan database models.

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
    JSONB,
    UUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.base import Base


# Purpose: Persist execution plan records.
class ExecutionPlan(Base):
    __tablename__ = "execution_plans"

    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'pending_approval', 'approved', 'rejected', 'superseded')",
            name="ck_execution_plans_status",
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

    repository_owner: Mapped[str] = mapped_column(
        String(100),
    )

    repository_name: Mapped[str] = mapped_column(
        String(100),
    )

    issue_number: Mapped[int] = mapped_column(
        Integer,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending_approval",
        index=True,
    )

    summary: Mapped[str] = mapped_column(
        Text
    )

    problem_analysis: Mapped[str] = mapped_column(
        Text
    )

    likely_root_cause: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confidence: Mapped[float] = mapped_column(
        Float
    )

    plan_json: Mapped[dict] = mapped_column(
        JSONB
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    planner_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    planner_latency_ms: Mapped[float | None] = mapped_column(
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
