"""add publications

Revision ID: b2c3d4e5f607
Revises: a1b2c3d4e5f6
Create Date: 2026-07-29

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b2c3d4e5f607"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publications",
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
            "review_id",
            postgresql.UUID(as_uuid=True),
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
            "status",
            sa.String(length=30),
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
            "base_branch",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "branch_name",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "base_commit_sha",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "approved_diff_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "working_tree_diff_hash",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "staged_diff_hash",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "commit_diff_hash",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "commit_sha",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "remote_head_sha",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "pull_request_number",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "pull_request_url",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "remote_branch_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "pr_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "error_message",
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
            "status in ('pending', 'publishing', 'local_committed', 'pushed', 'published', 'failed', 'partially_published')",
            name="ck_publications_status",
        ),
        sa.ForeignKeyConstraint(
            ["change_set_id"],
            ["change_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["execution_plans.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["final_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_id",
            name="uq_publications_review_id",
        ),
    )
    op.create_index(
        op.f("ix_publications_change_set_id"),
        "publications",
        ["change_set_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_publications_commit_sha"),
        "publications",
        ["commit_sha"],
        unique=False,
    )
    op.create_index(
        op.f("ix_publications_plan_id"),
        "publications",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_publications_pull_request_number"),
        "publications",
        ["pull_request_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_publications_review_id"),
        "publications",
        ["review_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_publications_status"),
        "publications",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_publications_workspace_id"),
        "publications",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_publications_workspace_id"),
        table_name="publications",
    )
    op.drop_index(
        op.f("ix_publications_status"),
        table_name="publications",
    )
    op.drop_index(
        op.f("ix_publications_review_id"),
        table_name="publications",
    )
    op.drop_index(
        op.f("ix_publications_pull_request_number"),
        table_name="publications",
    )
    op.drop_index(
        op.f("ix_publications_plan_id"),
        table_name="publications",
    )
    op.drop_index(
        op.f("ix_publications_commit_sha"),
        table_name="publications",
    )
    op.drop_index(
        op.f("ix_publications_change_set_id"),
        table_name="publications",
    )
    op.drop_table("publications")
