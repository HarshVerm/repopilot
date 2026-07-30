# Module purpose: Implement github tokens behavior for the authentication domain.

import base64
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.identity import (
    GitHubUserAuthorization,
)
from app.observability.logging import log_task_event


ACTIVE = "active"
REAUTHORIZATION_REQUIRED = "reauthorization_required"
REVOKED = "revoked"
TOKEN_REFRESH_LEEWAY = timedelta(minutes=5)


# Purpose: Encapsulate git hub user authorization required behavior for the authentication domain.
class GitHubUserAuthorizationRequired(RuntimeError):
    pass


# Purpose: Encapsulate git hub user authorization unavailable behavior for the authentication domain.
class GitHubUserAuthorizationUnavailable(RuntimeError):
    pass


# Purpose: Encapsulate git hub o auth token set behavior for the authentication domain.
@dataclass(frozen=True)
class GitHubOAuthTokenSet:
    access_token: str
    access_token_expires_at: datetime | None = None
    refresh_token: str | None = None
    refresh_token_expires_at: datetime | None = None
    token_type: str = "bearer"

    # Purpose: Handle from payload for the authentication workflow.
    @classmethod
    def from_payload(
        cls,
        payload: dict,
        *,
        now: datetime | None = None,
    ) -> "GitHubOAuthTokenSet":
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubUserAuthorizationRequired(
                str(
                    payload.get("error_description")
                    or payload.get("error")
                    or "GitHub did not return a user access token."
                )
            )
        current_time = now or datetime.now(UTC)
        return cls(
            access_token=access_token,
            access_token_expires_at=expiry_from_seconds(
                payload.get("expires_in"),
                now=current_time,
            ),
            refresh_token=optional_string(
                payload.get("refresh_token")
            ),
            refresh_token_expires_at=expiry_from_seconds(
                payload.get("refresh_token_expires_in"),
                now=current_time,
            ),
            token_type=str(
                payload.get("token_type") or "bearer"
            ),
        )


# Purpose: Encapsulate git hub user authorization status behavior for the authentication domain.
@dataclass(frozen=True)
class GitHubUserAuthorizationStatus:
    connected: bool
    status: str
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None


# Purpose: Encapsulate git hub token cipher behavior for the authentication domain.
class GitHubTokenCipher:
    # Purpose: Initialize git hub token cipher state and dependencies.
    def __init__(
        self,
        secret: str | None = None,
    ) -> None:
        configured_secret = (
            secret
            or settings.github_user_token_encryption_secret
            or settings.session_secret
        )
        digest = hashlib.sha256(
            b"repopilot:github-user-token:v1\0"
            + configured_secret.encode("utf-8")
        ).digest()
        self._fernet = Fernet(
            base64.urlsafe_b64encode(digest)
        )

    # Purpose: Encrypt authentication for the authentication workflow.
    def encrypt(self, token: str) -> str:
        return self._fernet.encrypt(
            token.encode("utf-8")
        ).decode("ascii")

    # Purpose: Decrypt authentication for the authentication workflow.
    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(
                ciphertext.encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise GitHubUserAuthorizationRequired(
                "Stored GitHub authorization cannot be decrypted. "
                "Reconnect your GitHub account."
            ) from exc


# Purpose: Coordinate git hub user token operations.
class GitHubUserTokenService:
    # Purpose: Initialize git hub user token service state and dependencies.
    def __init__(
        self,
        *,
        cipher: GitHubTokenCipher | None = None,
        http_client_factory: Callable[..., httpx.AsyncClient]
        | None = None,
    ) -> None:
        self.cipher = cipher or GitHubTokenCipher()
        self.http_client_factory = (
            http_client_factory or httpx.AsyncClient
        )

    # Purpose: Store authentication for the authentication workflow.
    async def store(
        self,
        *,
        user_id: uuid.UUID,
        token_set: GitHubOAuthTokenSet,
        db: AsyncSession,
    ) -> GitHubUserAuthorization:
        authorization = await db.scalar(
            select(GitHubUserAuthorization)
            .where(
                GitHubUserAuthorization.user_id == user_id
            )
            .with_for_update()
        )
        now = datetime.now(UTC)
        if authorization is None:
            authorization = GitHubUserAuthorization(
                user_id=user_id,
                access_token_ciphertext="",
            )
            db.add(authorization)
        authorization.access_token_ciphertext = (
            self.cipher.encrypt(token_set.access_token)
        )
        authorization.access_token_expires_at = (
            token_set.access_token_expires_at
        )
        authorization.refresh_token_ciphertext = (
            self.cipher.encrypt(token_set.refresh_token)
            if token_set.refresh_token
            else None
        )
        authorization.refresh_token_expires_at = (
            token_set.refresh_token_expires_at
        )
        authorization.token_type = token_set.token_type
        authorization.status = ACTIVE
        authorization.authorized_at = now
        authorization.revoked_at = None
        await db.commit()
        await db.refresh(authorization)
        log_task_event(
            "github.user_authorization_stored",
            user_id=str(user_id),
            expiring=(
                token_set.access_token_expires_at
                is not None
            ),
            refreshable=token_set.refresh_token is not None,
        )
        return authorization

    # Purpose: Handle status for the authentication workflow.
    async def status(
        self,
        *,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> GitHubUserAuthorizationStatus:
        authorization = await db.scalar(
            select(GitHubUserAuthorization).where(
                GitHubUserAuthorization.user_id == user_id
            )
        )
        if authorization is None:
            return GitHubUserAuthorizationStatus(
                connected=False,
                status=REAUTHORIZATION_REQUIRED,
                access_token_expires_at=None,
                refresh_token_expires_at=None,
            )
        now = datetime.now(UTC)
        authorization_status = authorization.status
        access_expired = (
            authorization.access_token_expires_at is not None
            and authorization.access_token_expires_at <= now
        )
        refresh_unavailable = (
            authorization.refresh_token_ciphertext is None
            or (
                authorization.refresh_token_expires_at
                is not None
                and authorization.refresh_token_expires_at <= now
            )
        )
        if (
            authorization_status == ACTIVE
            and access_expired
            and refresh_unavailable
        ):
            authorization_status = REAUTHORIZATION_REQUIRED
        return GitHubUserAuthorizationStatus(
            connected=authorization_status == ACTIVE,
            status=authorization_status,
            access_token_expires_at=(
                authorization.access_token_expires_at
            ),
            refresh_token_expires_at=(
                authorization.refresh_token_expires_at
            ),
        )

    # Purpose: Handle access token for the authentication workflow.
    async def access_token(
        self,
        *,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> str:
        authorization = await db.scalar(
            select(GitHubUserAuthorization)
            .where(
                GitHubUserAuthorization.user_id == user_id
            )
            .with_for_update()
        )
        if (
            authorization is None
            or authorization.status != ACTIVE
        ):
            raise GitHubUserAuthorizationRequired(
                "Reconnect your GitHub account so RepoPilot can "
                "create the pull request as you."
            )

        now = datetime.now(UTC)
        expires_at = authorization.access_token_expires_at
        if (
            expires_at is None
            or expires_at > now + TOKEN_REFRESH_LEEWAY
        ):
            try:
                return self._decrypt_access_token(
                    authorization
                )
            except GitHubUserAuthorizationRequired:
                await self._require_reauthorization(
                    authorization=authorization,
                    db=db,
                    reason="access_token_decryption_failed",
                )
                raise AssertionError("unreachable")

        return await self._refresh(
            authorization=authorization,
            db=db,
            now=now,
        )

    # Purpose: Decrypt access token for the authentication workflow.
    def _decrypt_access_token(
        self,
        authorization: GitHubUserAuthorization,
    ) -> str:
        return self.cipher.decrypt(
            authorization.access_token_ciphertext
        )

    # Purpose: Refresh authentication for the authentication workflow.
    async def _refresh(
        self,
        *,
        authorization: GitHubUserAuthorization,
        db: AsyncSession,
        now: datetime,
    ) -> str:
        if (
            not settings.github_app_client_id
            or not settings.github_app_client_secret
        ):
            raise GitHubUserAuthorizationUnavailable(
                "GitHub user-token refresh is not configured."
            )
        if (
            authorization.refresh_token_ciphertext is None
            or (
                authorization.refresh_token_expires_at
                is not None
                and authorization.refresh_token_expires_at <= now
            )
        ):
            await self._require_reauthorization(
                authorization=authorization,
                db=db,
                reason="refresh_token_missing_or_expired",
            )
        try:
            refresh_token = self.cipher.decrypt(
                authorization.refresh_token_ciphertext
                or ""
            )
        except GitHubUserAuthorizationRequired:
            await self._require_reauthorization(
                authorization=authorization,
                db=db,
                reason="refresh_token_decryption_failed",
            )
            raise AssertionError("unreachable")

        try:
            async with self.http_client_factory(
                timeout=settings.github_timeout_seconds
            ) as client:
                response = await client.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": (
                            settings.github_app_client_id
                        ),
                        "client_secret": (
                            settings.github_app_client_secret
                        ),
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                )
        except httpx.HTTPError as exc:
            raise GitHubUserAuthorizationUnavailable(
                "GitHub authorization could not be refreshed."
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubUserAuthorizationUnavailable(
                "GitHub returned an invalid token refresh response."
            ) from exc
        if response.status_code >= 500:
            raise GitHubUserAuthorizationUnavailable(
                "GitHub authorization could not be refreshed."
            )
        if response.status_code >= 400 or payload.get("error"):
            await self._require_reauthorization(
                authorization=authorization,
                db=db,
                reason=str(
                    payload.get("error")
                    or f"github_http_{response.status_code}"
                ),
            )

        try:
            token_set = GitHubOAuthTokenSet.from_payload(
                payload,
                now=now,
            )
        except GitHubUserAuthorizationRequired:
            await self._require_reauthorization(
                authorization=authorization,
                db=db,
                reason="refresh_response_missing_token",
            )
            raise AssertionError("unreachable")

        authorization.access_token_ciphertext = (
            self.cipher.encrypt(token_set.access_token)
        )
        authorization.access_token_expires_at = (
            token_set.access_token_expires_at
        )
        authorization.refresh_token_ciphertext = (
            self.cipher.encrypt(token_set.refresh_token)
            if token_set.refresh_token
            else None
        )
        authorization.refresh_token_expires_at = (
            token_set.refresh_token_expires_at
        )
        authorization.token_type = token_set.token_type
        authorization.last_refreshed_at = now
        authorization.status = ACTIVE
        await db.commit()
        log_task_event(
            "github.user_authorization_refreshed",
            user_id=str(authorization.user_id),
        )
        return token_set.access_token

    # Purpose: Require reauthorization, raising an error when unavailable.
    async def _require_reauthorization(
        self,
        *,
        authorization: GitHubUserAuthorization,
        db: AsyncSession,
        reason: str,
    ) -> None:
        authorization.status = REAUTHORIZATION_REQUIRED
        authorization.access_token_ciphertext = ""
        authorization.access_token_expires_at = None
        authorization.refresh_token_ciphertext = None
        authorization.refresh_token_expires_at = None
        await db.commit()
        log_task_event(
            "github.user_authorization_invalidated",
            user_id=str(authorization.user_id),
            reason=reason[:100],
        )
        raise GitHubUserAuthorizationRequired(
            "Reconnect your GitHub account so RepoPilot can "
            "create the pull request as you."
        )


# Purpose: Handle expiry from seconds for the authentication workflow.
def expiry_from_seconds(
    value,
    *,
    now: datetime,
) -> datetime | None:
    if value is None:
        return None
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return now + timedelta(seconds=seconds)


# Purpose: Handle optional string for the authentication workflow.
def optional_string(value) -> str | None:
    return value if isinstance(value, str) and value else None
