"""store encrypted GitHub user authorizations

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publications",
        sa.Column(
            "pull_request_author_login",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.create_table(
        "github_user_authorizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "access_token_ciphertext",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "access_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "refresh_token_ciphertext",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "refresh_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "token_type",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "authorized_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_refreshed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
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
            "status in ('active', 'reauthorization_required', 'revoked')",
            name="ck_github_user_authorizations_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            name="uq_github_user_authorizations_user_id",
        ),
    )
    op.create_index(
        op.f(
            "ix_github_user_authorizations_access_token_expires_at"
        ),
        "github_user_authorizations",
        ["access_token_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f(
            "ix_github_user_authorizations_refresh_token_expires_at"
        ),
        "github_user_authorizations",
        ["refresh_token_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_user_authorizations_status"),
        "github_user_authorizations",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_user_authorizations_user_id"),
        "github_user_authorizations",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_github_user_authorizations_user_id"),
        table_name="github_user_authorizations",
    )
    op.drop_index(
        op.f("ix_github_user_authorizations_status"),
        table_name="github_user_authorizations",
    )
    op.drop_index(
        op.f(
            "ix_github_user_authorizations_refresh_token_expires_at"
        ),
        table_name="github_user_authorizations",
    )
    op.drop_index(
        op.f(
            "ix_github_user_authorizations_access_token_expires_at"
        ),
        table_name="github_user_authorizations",
    )
    op.drop_table("github_user_authorizations")
    op.drop_column(
        "publications",
        "pull_request_author_login",
    )
