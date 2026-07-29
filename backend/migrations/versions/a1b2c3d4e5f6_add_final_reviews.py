"""add final reviews

Revision ID: a1b2c3d4e5f6
Revises: e4a9b8c7d610
Create Date: 2026-07-29

"""

import hashlib
from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "e4a9b8c7d610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "change_sets",
        sa.Column(
            "diff_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )
    backfill_change_set_diff_hashes()

    op.create_table(
        "final_reviews",
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
            "change_set_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "execution_run_id",
            postgresql.UUID(as_uuid=True),
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
            "diff_hash",
            sa.String(length=64),
            nullable=False,
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
            "summary",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "risk_summary",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "decision",
            sa.String(length=30),
            nullable=True,
        ),
        sa.Column(
            "rejection_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "files_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "verification_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "debug_history_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "issue_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "plan_snapshot_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "diff",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('pending_review', 'approved', 'rejected', 'superseded')",
            name="ck_final_reviews_status",
        ),
        sa.CheckConstraint(
            "decision is null or decision in ('approved', 'rejected')",
            name="ck_final_reviews_decision",
        ),
        sa.ForeignKeyConstraint(
            ["change_set_id"],
            ["change_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["execution_run_id"],
            ["execution_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["execution_plans.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_final_reviews_change_set_id"),
        "final_reviews",
        ["change_set_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_final_reviews_diff_hash"),
        "final_reviews",
        ["diff_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_final_reviews_execution_run_id"),
        "final_reviews",
        ["execution_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_final_reviews_plan_id"),
        "final_reviews",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_final_reviews_status"),
        "final_reviews",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_final_reviews_workspace_id"),
        "final_reviews",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ux_final_reviews_active_exact_diff",
        "final_reviews",
        [
            "change_set_id",
            "diff_hash",
            "base_commit_sha",
        ],
        unique=True,
        postgresql_where=sa.text(
            "status in ('pending_review', 'approved')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_final_reviews_active_exact_diff",
        table_name="final_reviews",
    )
    op.drop_index(
        op.f("ix_final_reviews_workspace_id"),
        table_name="final_reviews",
    )
    op.drop_index(
        op.f("ix_final_reviews_status"),
        table_name="final_reviews",
    )
    op.drop_index(
        op.f("ix_final_reviews_plan_id"),
        table_name="final_reviews",
    )
    op.drop_index(
        op.f("ix_final_reviews_execution_run_id"),
        table_name="final_reviews",
    )
    op.drop_index(
        op.f("ix_final_reviews_diff_hash"),
        table_name="final_reviews",
    )
    op.drop_index(
        op.f("ix_final_reviews_change_set_id"),
        table_name="final_reviews",
    )
    op.drop_table("final_reviews")
    op.drop_column(
        "change_sets",
        "diff_hash",
    )


def backfill_change_set_diff_hashes() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "select id, diff from change_sets where diff is not null"
        )
    ).mappings()

    for row in rows:
        normalized = row["diff"].replace(
            "\r\n",
            "\n",
        ).strip()
        value = hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()
        connection.execute(
            sa.text(
                "update change_sets set diff_hash = :diff_hash where id = :id"
            ),
            {
                "diff_hash": value,
                "id": row["id"],
            },
        )
