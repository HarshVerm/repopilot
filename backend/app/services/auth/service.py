# Module purpose: Implement service behavior for the authentication domain.

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.identity import OAuthState, User, UserSession
from app.db.session import get_db
from app.services.auth.github_tokens import (
    GitHubOAuthTokenSet,
    GitHubUserAuthorizationRequired,
)


AUTH_REQUIRED = "AUTH_REQUIRED"
SESSION_EXPIRED = "SESSION_EXPIRED"
CSRF_FAILED = "CSRF_FAILED"


# Purpose: Represent auth context data.
@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


# Purpose: Handle secret hash for the authentication workflow.
def secret_hash(value: str) -> str:
    return hmac.new(
        settings.session_secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# Purpose: Handle auth error for the authentication workflow.
def auth_error(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
        headers={"X-Error-Code": code},
    )


# Purpose: Coordinate auth operations.
class AuthService:
    # Purpose: Create oauth state for the authentication workflow.
    async def create_oauth_state(
        self,
        *,
        db: AsyncSession,
        redirect_path: str = "/tasks",
        purpose: str = "login",
        user_id: uuid.UUID | None = None,
        github_installation_id: int | None = None,
    ) -> str:
        state = secrets.token_urlsafe(32)
        record = OAuthState(
            state_hash=secret_hash(state),
            redirect_path=safe_redirect_path(redirect_path),
            purpose=purpose,
            user_id=user_id,
            github_installation_id=github_installation_id,
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.oauth_state_expiry_minutes),
        )
        db.add(record)
        await db.commit()
        return state

    # Purpose: Consume oauth state for the authentication workflow.
    async def consume_oauth_state(
        self,
        *,
        state: str,
        db: AsyncSession,
        purpose: str | None,
        user_id: uuid.UUID | None = None,
    ) -> OAuthState:
        now = datetime.now(UTC)
        filters = [
            OAuthState.state_hash == secret_hash(state),
            OAuthState.used_at.is_(None),
            OAuthState.expires_at > now,
        ]
        if purpose is not None:
            filters.append(OAuthState.purpose == purpose)
        record = await db.scalar(
            select(OAuthState)
            .where(*filters)
            .with_for_update()
        )
        if record is None:
            raise auth_error(
                status_code=400,
                code="OAUTH_STATE_INVALID",
                message="The GitHub authorization request expired or is invalid.",
            )
        if record.user_id is not None and record.user_id != user_id:
            raise auth_error(
                status_code=400,
                code="OAUTH_STATE_INVALID",
                message="The GitHub authorization request does not match this user.",
            )
        record.used_at = now
        await db.commit()
        return record

    # Purpose: Handle github login url for the authentication workflow.
    def github_login_url(self, state: str) -> str:
        if not settings.github_app_client_id:
            raise auth_error(
                status_code=503,
                code="GITHUB_AUTH_NOT_CONFIGURED",
                message="GitHub authentication is not configured.",
            )
        query = urlencode(
            {
                "client_id": settings.github_app_client_id,
                "redirect_uri": (
                    f"{settings.app_base_url.rstrip('/')}"
                    "/api/v1/auth/github/callback"
                ),
                "state": state,
            }
        )
        return f"https://github.com/login/oauth/authorize?{query}"

    # Purpose: Exchange code for the authentication workflow.
    async def exchange_code(
        self,
        code: str,
    ) -> GitHubOAuthTokenSet:
        if (
            not settings.github_app_client_id
            or not settings.github_app_client_secret
        ):
            raise auth_error(
                status_code=503,
                code="GITHUB_AUTH_NOT_CONFIGURED",
                message="GitHub authentication is not configured.",
            )
        async with httpx.AsyncClient(
            timeout=settings.github_timeout_seconds
        ) as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_app_client_id,
                    "client_secret": settings.github_app_client_secret,
                    "code": code,
                    "redirect_uri": (
                        f"{settings.app_base_url.rstrip('/')}"
                        "/api/v1/auth/github/callback"
                    ),
                },
            )
            response.raise_for_status()
            payload = response.json()
        try:
            return GitHubOAuthTokenSet.from_payload(
                payload
            )
        except GitHubUserAuthorizationRequired as exc:
            raise auth_error(
                status_code=401,
                code="GITHUB_OAUTH_FAILED",
                message="GitHub did not authorize this login.",
            ) from exc

    # Purpose: Fetch github identity for the authentication workflow.
    async def fetch_github_identity(
        self,
        access_token: str,
    ) -> tuple[dict, str | None, list[dict]]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=settings.github_timeout_seconds,
        ) as client:
            user_response = await client.get("/user")
            user_response.raise_for_status()
            user_data = user_response.json()

            email = user_data.get("email")
            if not email:
                email_response = await client.get("/user/emails")
                if email_response.status_code == 200:
                    email = preferred_email(email_response.json())

            installations: list[dict] = []
            for page in range(1, 11):
                installations_response = await client.get(
                    "/user/installations",
                    params={
                        "per_page": "100",
                        "page": str(page),
                    },
                )
                if installations_response.status_code != 200:
                    break
                page_items = list(
                    installations_response.json().get(
                        "installations",
                        [],
                    )
                )
                installations.extend(page_items)
                if len(page_items) < 100:
                    break

        return user_data, email, installations

    # Purpose: Create or update user for the authentication workflow.
    async def upsert_user(
        self,
        *,
        github_user: dict,
        email: str | None,
        db: AsyncSession,
    ) -> User:
        github_user_id = int(github_user["id"])
        user = await db.scalar(
            select(User).where(
                User.github_user_id == github_user_id
            )
        )
        now = datetime.now(UTC)
        if user is None:
            user = User(
                github_user_id=github_user_id,
                github_login=str(github_user["login"]),
            )
            db.add(user)
        user.github_login = str(github_user["login"])
        user.github_name = github_user.get("name")
        user.github_avatar_url = github_user.get("avatar_url")
        user.github_email = email
        user.is_active = True
        user.last_login_at = now
        await db.commit()
        await db.refresh(user)
        return user

    # Purpose: Create session for the authentication workflow.
    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> tuple[UserSession, str, str]:
        token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        session = UserSession(
            user_id=user_id,
            token_hash=secret_hash(token),
            csrf_token_hash=secret_hash(csrf_token),
            expires_at=datetime.now(UTC)
            + timedelta(hours=settings.session_expiry_hours),
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session, token, csrf_token

    # Purpose: Revoke session for the authentication workflow.
    async def revoke_session(
        self,
        *,
        session: UserSession,
        db: AsyncSession,
    ) -> None:
        session.revoked_at = datetime.now(UTC)
        await db.commit()


# Purpose: Return optional auth context for the authentication workflow.
async def get_optional_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthContext | None:
    token = request.cookies.get(
        settings.session_cookie_name
    )
    if not token:
        return None
    now = datetime.now(UTC)
    session = await db.scalar(
        select(UserSession).where(
            UserSession.token_hash == secret_hash(token)
        )
    )
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
    ):
        raise auth_error(
            status_code=401,
            code=SESSION_EXPIRED,
            message="Your RepoPilot session expired. Sign in again.",
        )
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise auth_error(
            status_code=401,
            code=AUTH_REQUIRED,
            message="Sign in with GitHub to continue.",
        )
    return AuthContext(user=user, session=session)


# Purpose: Require auth context, raising an error when unavailable.
async def require_auth_context(
    context: AuthContext | None = Depends(
        get_optional_auth_context
    ),
) -> AuthContext:
    if context is None:
        raise auth_error(
            status_code=401,
            code=AUTH_REQUIRED,
            message="Sign in with GitHub to continue.",
        )
    return context


# Purpose: Require current user, raising an error when unavailable.
async def require_current_user(
    context: AuthContext = Depends(require_auth_context),
) -> User:
    return context.user


# Purpose: Require csrf, raising an error when unavailable.
async def require_csrf(
    request: Request,
    context: AuthContext = Depends(require_auth_context),
) -> User:
    validate_csrf_tokens(
        request=request,
        context=context,
    )
    return context.user


# Purpose: Validate csrf tokens for the authentication workflow.
def validate_csrf_tokens(
    *,
    request: Request,
    context: AuthContext,
) -> None:
    cookie_token = request.cookies.get(
        settings.csrf_cookie_name
    )
    header_token = request.headers.get(
        settings.csrf_header_name
    )
    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(
            cookie_token,
            header_token,
        )
        or not secrets.compare_digest(
            secret_hash(cookie_token),
            context.session.csrf_token_hash,
        )
    ):
        raise auth_error(
            status_code=403,
            code=CSRF_FAILED,
            message="The request could not be verified. Refresh and try again.",
        )


# Purpose: Handle preferred email for the authentication workflow.
def preferred_email(emails: list[dict]) -> str | None:
    verified = [
        item
        for item in emails
        if item.get("verified") and item.get("email")
    ]
    primary = next(
        (item for item in verified if item.get("primary")),
        None,
    )
    selected = primary or (verified[0] if verified else None)
    return str(selected["email"]) if selected else None


# Purpose: Handle safe redirect path for the authentication workflow.
def safe_redirect_path(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        return "/tasks"
    return path[:500]
