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
    relationship,
)

from app.db.base import Base


class ChangeSet(Base):
    __tablename__ = "change_sets"

    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'generating', 'generated', 'validation_failed', 'failed')",
            name="ck_change_sets_status",
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

    parent_change_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "change_sets.id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=True,
    )

    plan_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )

    approved_plan_json: Mapped[dict] = mapped_column(
        JSONB
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )

    base_commit_sha: Mapped[str] = mapped_column(
        String(64)
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    diff: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    diff_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
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

    before_tree_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    after_tree_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    coder_model: Mapped[str | None] = mapped_column(
        String(100),
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

    patch_operations_requested: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    patch_operations_accepted: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    patch_operations_rejected: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    diagnostics: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    revision_reason: Mapped[str | None] = mapped_column(
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

    files = relationship(
        "ChangeSetFile",
        back_populates="change_set",
        cascade="all, delete-orphan",
    )


class ChangeSetFile(Base):
    __tablename__ = "change_set_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    change_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "change_sets.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    path: Mapped[str] = mapped_column(
        Text
    )

    before_sha256: Mapped[str] = mapped_column(
        String(64)
    )

    after_sha256: Mapped[str] = mapped_column(
        String(64)
    )

    lines_added: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    lines_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    change_set = relationship(
        "ChangeSet",
        back_populates="files",
    )
