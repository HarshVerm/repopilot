"""add execution plans

Revision ID: f2c8a1d4b905
Revises: e7b9c4d2a103
Create Date: 2026-07-29

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2c8a1d4b905"
down_revision: str | None = "e7b9c4d2a103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_plans",
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
            "repository_owner",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "repository_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "issue_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "summary",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "problem_analysis",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "likely_root_cause",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "plan_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "rejection_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "planner_model",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "planner_latency_ms",
            sa.Float(),
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
            "status in ('draft', 'pending_approval', 'approved', 'rejected', 'superseded')",
            name="ck_execution_plans_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_execution_plans_issue_number"),
        "execution_plans",
        ["issue_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_plans_status"),
        "execution_plans",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_plans_workspace_id"),
        "execution_plans",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_execution_plans_workspace_id"),
        table_name="execution_plans",
    )
    op.drop_index(
        op.f("ix_execution_plans_status"),
        table_name="execution_plans",
    )
    op.drop_index(
        op.f("ix_execution_plans_issue_number"),
        table_name="execution_plans",
    )
    op.drop_table("execution_plans")
