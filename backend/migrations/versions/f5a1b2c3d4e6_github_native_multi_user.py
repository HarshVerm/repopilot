"""add GitHub-native multi-user ownership

Revision ID: f5a1b2c3d4e6
Revises: d4e5f6071829
Create Date: 2026-07-29

Existing tasks intentionally remain unowned. Production deployments must
backfill or archive those rows deliberately; the application never assigns
them to an arbitrary user.
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f5a1b2c3d4e6"
down_revision: str | None = "d4e5f6071829"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_TASK_STATUS_CHECK = (
    "status in ('created', 'repository_preparing', 'repository_ready', "
    "'indexing', 'indexed', 'retrieving', 'planning', "
    "'plan_pending_approval', 'plan_approved', 'plan_rejected', "
    "'plan_revision_required', 'coding', 'patch_generated', 'testing', "
    "'test_failed', 'debugging', 'verification_passed', 'review_pending', "
    "'review_approved', 'review_rejected', 'publishing', 'completed', "
    "'failed', 'cancelled')"
)

OLD_TASK_STATUS_CHECK = (
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
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("github_login", sa.String(length=255), nullable=False),
        sa.Column("github_name", sa.String(length=255), nullable=True),
        sa.Column("github_avatar_url", sa.Text(), nullable=True),
        sa.Column("github_email", sa.String(length=320), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "last_login_at",
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_user_id"),
    )
    op.create_index(
        op.f("ix_users_github_user_id"),
        "users",
        ["github_user_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_users_github_login"),
        "users",
        ["github_login"],
        unique=False,
    )

    op.create_table(
        "oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "purpose",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "redirect_path",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index(
        op.f("ix_oauth_states_state_hash"),
        "oauth_states",
        ["state_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_oauth_states_expires_at"),
        "oauth_states",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_states_user_id"),
        "oauth_states",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_user_sessions_user_id"),
        "user_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_sessions_token_hash"),
        "user_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_user_sessions_expires_at"),
        "user_sessions",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "github_installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "github_installation_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_account_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "github_account_login",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("account_type", sa.String(length=30), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=True),
        sa.Column(
            "repository_selection",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "suspended_at",
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
            "status in ('active', 'suspended', 'removed', "
            "'permission_error', 'approval_required')",
            name="ck_github_installations_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "github_installation_id",
            name="uq_github_installations_user_external",
        ),
    )
    for column in (
        "github_installation_id",
        "user_id",
        "github_account_id",
        "status",
    ):
        op.create_index(
            op.f(f"ix_github_installations_{column}"),
            "github_installations",
            [column],
            unique=False,
        )

    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=511), nullable=False),
        sa.Column("private", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column(
            "access_status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "default_branch",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("clone_url", sa.Text(), nullable=True),
        sa.Column(
            "permissions_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at",
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
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["github_installations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "access_status in ('active', 'removed', 'permission_error')",
            name="ck_repositories_access_status",
        ),
        sa.UniqueConstraint(
            "installation_id",
            "github_repository_id",
            name="uq_repositories_installation_external",
        ),
    )
    for column in (
        "installation_id",
        "github_repository_id",
        "owner",
        "name",
        "full_name",
        "archived",
        "access_status",
    ):
        op.create_index(
            op.f(f"ix_repositories_{column}"),
            "repositories",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_repositories_full_name_search",
        "repositories",
        ["full_name"],
        unique=False,
    )

    task_columns = (
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("github_issue_id", sa.BigInteger(), nullable=True),
        sa.Column("issue_title", sa.String(length=300), nullable=True),
        sa.Column("issue_body_snapshot", sa.Text(), nullable=True),
        sa.Column("issue_url", sa.Text(), nullable=True),
        sa.Column("issue_author", sa.String(length=255), nullable=True),
        sa.Column(
            "issue_labels",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "issue_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "issue_updated_at_at_creation",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("issue_summary", sa.Text(), nullable=True),
        sa.Column("user_instructions", sa.Text(), nullable=True),
        sa.Column("base_branch", sa.String(length=255), nullable=True),
        sa.Column("base_commit_sha", sa.String(length=64), nullable=True),
        sa.Column(
            "autonomy_mode",
            sa.String(length=20),
            server_default="strict",
            nullable=False,
        ),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    for column in task_columns:
        op.add_column("repo_pilot_tasks", column)

    for column, target, ondelete in (
        ("user_id", "users.id", "RESTRICT"),
        ("installation_id", "github_installations.id", "RESTRICT"),
        ("repository_id", "repositories.id", "RESTRICT"),
    ):
        table, target_column = target.split(".")
        op.create_foreign_key(
            f"fk_repo_pilot_tasks_{column}",
            "repo_pilot_tasks",
            table,
            [column],
            [target_column],
            ondelete=ondelete,
        )
        op.create_index(
            op.f(f"ix_repo_pilot_tasks_{column}"),
            "repo_pilot_tasks",
            [column],
            unique=False,
        )
    op.create_index(
        op.f("ix_repo_pilot_tasks_github_issue_id"),
        "repo_pilot_tasks",
        ["github_issue_id"],
        unique=False,
    )
    op.drop_constraint(
        "ck_repo_pilot_tasks_status",
        "repo_pilot_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "ck_repo_pilot_tasks_status",
        "repo_pilot_tasks",
        NEW_TASK_STATUS_CHECK,
    )

    op.add_column(
        "final_reviews",
        sa.Column(
            "review_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "final_reviews",
        sa.Column("feedback", sa.Text(), nullable=True),
    )
    op.add_column(
        "final_reviews",
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_final_reviews_reviewed_by_user_id",
        "final_reviews",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_final_reviews_reviewed_by_user_id"),
        "final_reviews",
        ["reviewed_by_user_id"],
        unique=False,
    )
    op.drop_constraint(
        "ck_final_reviews_status",
        "final_reviews",
        type_="check",
    )
    op.create_check_constraint(
        "ck_final_reviews_status",
        "final_reviews",
        "status in ('pending_review', 'approved', 'rejected', "
        "'changes_requested', 'superseded')",
    )
    op.drop_constraint(
        "ck_final_reviews_decision",
        "final_reviews",
        type_="check",
    )
    op.create_check_constraint(
        "ck_final_reviews_decision",
        "final_reviews",
        "decision is null or decision in "
        "('approved', 'rejected', 'changes_requested')",
    )

    for column in (
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "publication_attempt_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("failure_stage", sa.String(length=60), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
    ):
        op.add_column("publications", column)
    for column, table in (
        ("installation_id", "github_installations"),
        ("repository_id", "repositories"),
    ):
        op.create_foreign_key(
            f"fk_publications_{column}",
            "publications",
            table,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            op.f(f"ix_publications_{column}"),
            "publications",
            [column],
            unique=False,
        )
    op.create_index(
        op.f("ix_publications_publication_attempt_id"),
        "publications",
        ["publication_attempt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_publications_publication_attempt_id"),
        table_name="publications",
    )
    for column in ("repository_id", "installation_id"):
        op.drop_index(
            op.f(f"ix_publications_{column}"),
            table_name="publications",
        )
        op.drop_constraint(
            f"fk_publications_{column}",
            "publications",
            type_="foreignkey",
        )
    for column in (
        "failure_reason",
        "failure_stage",
        "publication_attempt_id",
        "repository_id",
        "installation_id",
    ):
        op.drop_column("publications", column)

    op.drop_constraint(
        "ck_final_reviews_decision",
        "final_reviews",
        type_="check",
    )
    op.create_check_constraint(
        "ck_final_reviews_decision",
        "final_reviews",
        "decision is null or decision in ('approved', 'rejected')",
    )
    op.drop_constraint(
        "ck_final_reviews_status",
        "final_reviews",
        type_="check",
    )
    op.create_check_constraint(
        "ck_final_reviews_status",
        "final_reviews",
        "status in ('pending_review', 'approved', 'rejected', 'superseded')",
    )
    op.drop_index(
        op.f("ix_final_reviews_reviewed_by_user_id"),
        table_name="final_reviews",
    )
    op.drop_constraint(
        "fk_final_reviews_reviewed_by_user_id",
        "final_reviews",
        type_="foreignkey",
    )
    for column in ("reviewed_by_user_id", "feedback", "review_version"):
        op.drop_column("final_reviews", column)

    op.drop_constraint(
        "ck_repo_pilot_tasks_status",
        "repo_pilot_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "ck_repo_pilot_tasks_status",
        "repo_pilot_tasks",
        OLD_TASK_STATUS_CHECK,
    )
    op.drop_index(
        op.f("ix_repo_pilot_tasks_github_issue_id"),
        table_name="repo_pilot_tasks",
    )
    for column in ("repository_id", "installation_id", "user_id"):
        op.drop_index(
            op.f(f"ix_repo_pilot_tasks_{column}"),
            table_name="repo_pilot_tasks",
        )
        op.drop_constraint(
            f"fk_repo_pilot_tasks_{column}",
            "repo_pilot_tasks",
            type_="foreignkey",
        )
    for column in (
        "cancelled_at",
        "autonomy_mode",
        "base_commit_sha",
        "base_branch",
        "user_instructions",
        "issue_summary",
        "issue_updated_at_at_creation",
        "issue_created_at",
        "issue_labels",
        "issue_author",
        "issue_url",
        "issue_body_snapshot",
        "issue_title",
        "github_issue_id",
        "repository_id",
        "installation_id",
        "user_id",
    ):
        op.drop_column("repo_pilot_tasks", column)

    op.drop_index(
        "ix_repositories_full_name_search",
        table_name="repositories",
    )
    op.drop_table("repositories")
    op.drop_table("github_installations")
    op.drop_table("user_sessions")
    op.drop_table("oauth_states")
    op.drop_table("users")
