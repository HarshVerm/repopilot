# Module purpose: Define persistent evaluation task result database models.

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
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


# Purpose: Persist evaluation task result records.
class EvaluationTaskResult(Base):
    __tablename__ = "evaluation_task_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "evaluation_runs.id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    evaluation_task_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        index=True,
    )
    difficulty: Mapped[str] = mapped_column(
        String(20),
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(80),
        index=True,
    )
    repo_pilot_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "repo_pilot_tasks.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    retrieval_recall_at_1: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )
    retrieval_recall_at_3: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )
    retrieval_recall_at_5: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )
    retrieval_recall_at_10: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )
    retrieval_precision_at_5: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    planner_relevant_file_recall: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )
    planner_hallucinated_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    planner_extra_modify_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    first_patch_passed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    debug_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    debug_recovered: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    visible_tests_passed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    hidden_tests_passed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    final_success: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )
    files_changed: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    lines_added: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    lines_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    cost: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    failure_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    security_violations_attempted: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    security_violations_applied: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
