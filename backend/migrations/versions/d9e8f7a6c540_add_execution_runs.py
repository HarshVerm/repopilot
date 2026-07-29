"""add execution runs

Revision ID: d9e8f7a6c540
Revises: a6d5e4c3b210
Create Date: 2026-07-29

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d9e8f7a6c540"
down_revision: str | None = "a6d5e4c3b210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_runs",
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
            "workspace_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "duration_ms",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "commands_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "results_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "tests_status",
            sa.String(length=20),
            nullable=True,
        ),
        sa.Column(
            "lint_status",
            sa.String(length=20),
            nullable=True,
        ),
        sa.Column(
            "typecheck_status",
            sa.String(length=20),
            nullable=True,
        ),
        sa.Column(
            "build_status",
            sa.String(length=20),
            nullable=True,
        ),
        sa.Column(
            "timed_out",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "sandbox_runtime",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "runtime_metadata",
            postgresql.JSONB(),
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
            "status in ('pending', 'running', 'passed', 'failed', 'timeout', 'error')",
            name="ck_execution_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["change_set_id"],
            ["change_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_execution_runs_change_set_id"),
        "execution_runs",
        ["change_set_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_runs_status"),
        "execution_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_runs_workspace_id"),
        "execution_runs",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_execution_runs_workspace_id"),
        table_name="execution_runs",
    )
    op.drop_index(
        op.f("ix_execution_runs_status"),
        table_name="execution_runs",
    )
    op.drop_index(
        op.f("ix_execution_runs_change_set_id"),
        table_name="execution_runs",
    )
    op.drop_table("execution_runs")
