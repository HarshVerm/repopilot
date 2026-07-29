"""prevent duplicate active GitHub-native tasks

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTIVE_NATIVE_TASK_PREDICATE = (
    "user_id is not null and repository_id is not null and "
    "status not in ('completed', 'plan_rejected', 'review_rejected', "
    "'failed', 'cancelled')"
)


def upgrade() -> None:
    op.create_index(
        "ux_repo_pilot_tasks_native_active_issue",
        "repo_pilot_tasks",
        ["user_id", "repository_id", "issue_number"],
        unique=True,
        postgresql_where=sa.text(
            ACTIVE_NATIVE_TASK_PREDICATE
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_repo_pilot_tasks_native_active_issue",
        table_name="repo_pilot_tasks",
    )
