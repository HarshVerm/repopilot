"""add tasks observability

Revision ID: c3d4e5f60718
Revises: b2c3d4e5f607
Create Date: 2026-07-29

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3d4e5f60718"
down_revision: str | None = "b2c3d4e5f607"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TASK_STATUS_CHECK = (
    "status in ('created', 'repository_preparing', 'repository_ready', "
    "'indexing', 'indexed', 'retrieving', 'planning', "
    "'plan_pending_approval', 'plan_approved', 'plan_rejected', "
    "'coding', 'patch_generated', 'testing', 'test_failed', "
    "'debugging', 'verification_passed', 'review_pending', "
    "'review_approved', 'review_rejected', 'publishing', 'completed', "
    "'failed', 'cancelled')"
)


def upgrade() -> None:
    op.create_table(
        "repo_pilot_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
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
            "workspace_id",
            sa.String(length=36),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
        ),
        sa.Column(
            "current_step",
            sa.Integer(),
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
            "last_error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "last_error_type",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "failure_category",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "retryable",
            sa.Boolean(),
            nullable=True,
        ),
        sa.Column(
            "active_plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "active_change_set_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "active_execution_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "active_review_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "last_event_at",
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
            TASK_STATUS_CHECK,
            name="ck_repo_pilot_tasks_status",
        ),
        sa.ForeignKeyConstraint(
            ["active_change_set_id"],
            ["change_sets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["active_execution_run_id"],
            ["execution_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["active_plan_id"],
            ["execution_plans.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["active_review_id"],
            ["final_reviews.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["publication_id"],
            ["publications.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_owner",
            "repository_name",
            "issue_number",
            "completed_at",
            name="uq_repo_pilot_tasks_issue_completed_at",
        ),
    )
    create_task_indexes()

    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "agent_type",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "model",
            sa.String(length=100),
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
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "latency_ms",
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
            "tool_calls_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "error_type",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "change_set_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "debug_attempt_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "request_id",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "correlation_id",
            sa.String(length=100),
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
            "agent_type in ('planner', 'coder', 'debugger')",
            name="ck_agent_runs_agent_type",
        ),
        sa.CheckConstraint(
            "status in ('started', 'completed', 'failed', 'cancelled')",
            name="ck_agent_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["change_set_id"],
            ["change_sets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["debug_attempt_id"],
            ["debug_attempts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["execution_plans.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["repo_pilot_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    create_agent_run_indexes()

    op.create_table(
        "task_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "step",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=True,
        ),
        sa.Column(
            "message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "correlation_id",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["repo_pilot_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    create_task_event_indexes()

    op.create_table(
        "task_operation_locks",
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "operation",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "owner",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "acquired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["repo_pilot_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(
        op.f("ix_task_operation_locks_expires_at"),
        "task_operation_locks",
        ["expires_at"],
        unique=False,
    )

    add_task_id_column(
        "execution_plans"
    )
    add_task_id_column(
        "change_sets"
    )
    add_task_id_column(
        "execution_runs"
    )
    add_task_id_column(
        "debug_attempts"
    )
    add_task_id_column(
        "final_reviews"
    )
    add_task_id_column(
        "publications"
    )


def downgrade() -> None:
    drop_task_id_column(
        "publications"
    )
    drop_task_id_column(
        "final_reviews"
    )
    drop_task_id_column(
        "debug_attempts"
    )
    drop_task_id_column(
        "execution_runs"
    )
    drop_task_id_column(
        "change_sets"
    )
    drop_task_id_column(
        "execution_plans"
    )

    op.drop_index(
        op.f("ix_task_operation_locks_expires_at"),
        table_name="task_operation_locks",
    )
    op.drop_table(
        "task_operation_locks"
    )
    drop_task_event_indexes()
    op.drop_table(
        "task_events"
    )
    drop_agent_run_indexes()
    op.drop_table(
        "agent_runs"
    )
    drop_task_indexes()
    op.drop_table(
        "repo_pilot_tasks"
    )


def add_task_id_column(
    table_name: str,
) -> None:
    op.add_column(
        table_name,
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        f"fk_{table_name}_task_id_repo_pilot_tasks",
        table_name,
        "repo_pilot_tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f(f"ix_{table_name}_task_id"),
        table_name,
        ["task_id"],
        unique=False,
    )


def drop_task_id_column(
    table_name: str,
) -> None:
    op.drop_index(
        op.f(f"ix_{table_name}_task_id"),
        table_name=table_name,
    )
    op.drop_constraint(
        f"fk_{table_name}_task_id_repo_pilot_tasks",
        table_name,
        type_="foreignkey",
    )
    op.drop_column(
        table_name,
        "task_id",
    )


def create_task_indexes() -> None:
    for column in [
        "active_change_set_id",
        "active_execution_run_id",
        "active_plan_id",
        "active_review_id",
        "failure_category",
        "issue_number",
        "last_event_at",
        "publication_id",
        "repository_name",
        "repository_owner",
        "status",
        "workspace_id",
    ]:
        op.create_index(
            op.f(
                f"ix_repo_pilot_tasks_{column}"
            ),
            "repo_pilot_tasks",
            [column],
            unique=False,
        )


def drop_task_indexes() -> None:
    for column in [
        "workspace_id",
        "status",
        "repository_owner",
        "repository_name",
        "publication_id",
        "last_event_at",
        "issue_number",
        "failure_category",
        "active_review_id",
        "active_plan_id",
        "active_execution_run_id",
        "active_change_set_id",
    ]:
        op.drop_index(
            op.f(
                f"ix_repo_pilot_tasks_{column}"
            ),
            table_name="repo_pilot_tasks",
        )


def create_agent_run_indexes() -> None:
    for column in [
        "agent_type",
        "change_set_id",
        "correlation_id",
        "debug_attempt_id",
        "plan_id",
        "status",
        "task_id",
    ]:
        op.create_index(
            op.f(f"ix_agent_runs_{column}"),
            "agent_runs",
            [column],
            unique=False,
        )


def drop_agent_run_indexes() -> None:
    for column in [
        "task_id",
        "status",
        "plan_id",
        "debug_attempt_id",
        "correlation_id",
        "change_set_id",
        "agent_type",
    ]:
        op.drop_index(
            op.f(f"ix_agent_runs_{column}"),
            table_name="agent_runs",
        )


def create_task_event_indexes() -> None:
    for column in [
        "agent_run_id",
        "correlation_id",
        "created_at",
        "event_type",
        "task_id",
    ]:
        op.create_index(
            op.f(f"ix_task_events_{column}"),
            "task_events",
            [column],
            unique=False,
        )


def drop_task_event_indexes() -> None:
    for column in [
        "task_id",
        "event_type",
        "created_at",
        "correlation_id",
        "agent_run_id",
    ]:
        op.drop_index(
            op.f(f"ix_task_events_{column}"),
            table_name="task_events",
        )
