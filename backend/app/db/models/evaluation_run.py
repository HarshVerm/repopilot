# Module purpose: Define persistent evaluation run database models.

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
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


EVALUATION_RUN_STATUSES = (
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
)


# Purpose: Persist evaluation run records.
class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    __table_args__ = (
        CheckConstraint(
            "status in "
            + str(EVALUATION_RUN_STATUSES).replace(
                '"',
                "'",
            ),
            name="ck_evaluation_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    suite_name: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )
    suite_version: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )
    is_baseline: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )
    repopilot_commit_sha: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    planner_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    coder_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    debugger_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    configuration_json: Mapped[dict | None] = mapped_column(
        JSON,
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
    total_tasks: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    successful_tasks: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    first_pass_successes: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    debug_recoveries: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    total_input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    total_output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    total_cost: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    total_duration_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    report_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
