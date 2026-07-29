"""create code index tables

Revision ID: b4f6a8d2c901
Revises:
Create Date: 2026-07-29

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b4f6a8d2c901"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repository_files",
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
            "file_path",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "language",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "size_bytes",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "file_path",
        ),
    )
    op.create_index(
        op.f("ix_repository_files_workspace_id"),
        "repository_files",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "code_symbols",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "start_line",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "end_line",
            sa.Integer(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["repository_files.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_code_symbols_file_id"),
        "code_symbols",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_code_symbols_name"),
        "code_symbols",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_code_symbols_name"),
        table_name="code_symbols",
    )
    op.drop_index(
        op.f("ix_code_symbols_file_id"),
        table_name="code_symbols",
    )
    op.drop_table("code_symbols")

    op.drop_index(
        op.f("ix_repository_files_workspace_id"),
        table_name="repository_files",
    )
    op.drop_table("repository_files")
