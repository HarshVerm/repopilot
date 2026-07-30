# Module purpose: Define persistent identity database models.

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


# Purpose: Persist user records.
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("github_user_id"),
        Index(
            "ix_users_github_user_id",
            "github_user_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    github_user_id: Mapped[int] = mapped_column(
        BigInteger,
    )
    github_login: Mapped[str] = mapped_column(
        String(255),
        index=True,
    )
    github_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    github_avatar_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    github_email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# Purpose: Persist user session records.
class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        Index(
            "ix_user_sessions_token_hash",
            "token_hash",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
    )
    csrf_token_hash: Mapped[str] = mapped_column(
        String(64),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


# Purpose: Persist git hub user authorization records.
class GitHubUserAuthorization(Base):
    __tablename__ = "github_user_authorizations"
    __table_args__ = (
        CheckConstraint(
            "status in ('active', 'reauthorization_required', 'revoked')",
            name="ck_github_user_authorizations_status",
        ),
        UniqueConstraint(
            "user_id",
            name="uq_github_user_authorizations_user_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    access_token_ciphertext: Mapped[str] = mapped_column(
        Text,
    )
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    token_type: Mapped[str] = mapped_column(
        String(30),
        default="bearer",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
    )
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# Purpose: Persist o auth state records.
class OAuthState(Base):
    __tablename__ = "oauth_states"
    __table_args__ = (
        UniqueConstraint("state_hash"),
        Index(
            "ix_oauth_states_state_hash",
            "state_hash",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    state_hash: Mapped[str] = mapped_column(
        String(64),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    github_installation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(
        String(30),
        default="login",
    )
    redirect_path: Mapped[str] = mapped_column(
        String(500),
        default="/tasks",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


# Purpose: Persist git hub installation records.
class GitHubInstallation(Base):
    __tablename__ = "github_installations"
    __table_args__ = (
        CheckConstraint(
            "status in ('active', 'suspended', 'removed', "
            "'permission_error', 'approval_required')",
            name="ck_github_installations_status",
        ),
        UniqueConstraint(
            "user_id",
            "github_installation_id",
            name="uq_github_installations_user_external",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    github_installation_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    github_account_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )
    github_account_login: Mapped[str] = mapped_column(
        String(255),
    )
    account_type: Mapped[str] = mapped_column(
        String(30),
    )
    target_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    repository_selection: Mapped[str] = mapped_column(
        String(30),
        default="selected",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
    )
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# Purpose: Persist repository records.
class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        CheckConstraint(
            "access_status in ('active', 'removed', 'permission_error')",
            name="ck_repositories_access_status",
        ),
        UniqueConstraint(
            "installation_id",
            "github_repository_id",
            name="uq_repositories_installation_external",
        ),
        Index(
            "ix_repositories_full_name_search",
            "full_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "github_installations.id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    github_repository_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )
    owner: Mapped[str] = mapped_column(
        String(255),
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        index=True,
    )
    full_name: Mapped[str] = mapped_column(
        String(511),
        index=True,
    )
    private: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )
    disabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    access_status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
    )
    default_branch: Mapped[str] = mapped_column(
        String(255),
        default="main",
    )
    html_url: Mapped[str] = mapped_column(
        Text,
    )
    clone_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    permissions_json: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
