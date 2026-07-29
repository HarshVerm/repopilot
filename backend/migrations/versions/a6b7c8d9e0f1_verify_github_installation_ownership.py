"""verify GitHub installation ownership

Revision ID: a6b7c8d9e0f1
Revises: f5a1b2c3d4e6
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, None] = "f5a1b2c3d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "oauth_states",
        sa.Column(
            "github_installation_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_oauth_states_github_installation_id"),
        "oauth_states",
        ["github_installation_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_repo_pilot_tasks_autonomy_mode",
        "repo_pilot_tasks",
        "autonomy_mode in ('standard', 'strict')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_repo_pilot_tasks_autonomy_mode",
        "repo_pilot_tasks",
        type_="check",
    )
    op.drop_index(
        op.f("ix_oauth_states_github_installation_id"),
        table_name="oauth_states",
    )
    op.drop_column(
        "oauth_states",
        "github_installation_id",
    )
