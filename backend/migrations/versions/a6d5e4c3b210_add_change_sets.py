"""add change sets

Revision ID: a6d5e4c3b210
Revises: f2c8a1d4b905
Create Date: 2026-07-29

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a6d5e4c3b210"
down_revision: str | None = "f2c8a1d4b905"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "change_sets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "plan_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "approved_plan_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "base_commit_sha",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "summary",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "diff",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "files_changed",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "lines_added",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "lines_deleted",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "before_tree_hash",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "after_tree_hash",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "coder_model",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "total_tokens",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "latency_ms",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "patch_operations_requested",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "patch_operations_accepted",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "patch_operations_rejected",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "diagnostics",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "revision_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('pending', 'generating', 'generated', 'validation_failed', 'failed')",
            name="ck_change_sets_status",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["execution_plans.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_change_sets_plan_id"),
        "change_sets",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_change_sets_status"),
        "change_sets",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_change_sets_workspace_id"),
        "change_sets",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "change_set_files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "change_set_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "path",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "before_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "after_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "lines_added",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "lines_deleted",
            sa.Integer(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["change_set_id"],
            ["change_sets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_change_set_files_change_set_id"),
        "change_set_files",
        ["change_set_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_change_set_files_change_set_id"),
        table_name="change_set_files",
    )
    op.drop_table("change_set_files")
    op.drop_index(
        op.f("ix_change_sets_workspace_id"),
        table_name="change_sets",
    )
    op.drop_index(
        op.f("ix_change_sets_status"),
        table_name="change_sets",
    )
    op.drop_index(
        op.f("ix_change_sets_plan_id"),
        table_name="change_sets",
    )
    op.drop_table("change_sets")
