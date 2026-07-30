# Module purpose: Define auth HTTP API routes.

from urllib.parse import urlencode

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.identity import User
from app.db.session import get_db
from app.schemas.auth import (
    CurrentUserResponse,
    GitHubSetupResponse,
    GitHubUserAuthorizationResponse,
    LogoutResponse,
)
from app.services.auth.github_tokens import (
    GitHubUserTokenService,
)
from app.services.auth.service import (
    AuthContext,
    AuthService,
    auth_error,
    get_optional_auth_context,
    require_auth_context,
    require_csrf,
    require_current_user,
)
from app.services.github.installations import (
    InstallationService,
)
from app.services.github.app_client import (
    GitHubAppClient,
    GitHubAppConfigurationError,
    missing_github_app_settings,
)


router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)


# Purpose: Handle github login for the authentication workflow.
@router.get("/github/login")
async def github_login(
    redirect_to: str = Query(default="/tasks"),
    db: AsyncSession = Depends(get_db),
):
    if (
        not settings.github_app_client_id
        or not settings.github_app_client_secret
    ):
        return RedirectResponse(
            f"{settings.frontend_url.rstrip('/')}"
            "/login?error=github-auth-not-configured"
        )

    state = await AuthService().create_oauth_state(
        db=db,
        redirect_path=redirect_to,
    )
    return RedirectResponse(
        AuthService().github_login_url(state)
    )


# Purpose: Handle github callback for the authentication workflow.
@router.get("/github/callback")
async def github_callback(
    code: str,
    state: str,
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService()
    state_record = await service.consume_oauth_state(
        state=state,
        purpose=None,
        user_id=auth.user.id if auth else None,
        db=db,
    )
    if state_record.purpose not in {
        "login",
        "installation_verification",
        "user_authorization",
    }:
        raise auth_error(
            status_code=400,
            code="OAUTH_STATE_INVALID",
            message="The GitHub authorization request is invalid.",
        )
    try:
        token_set = await service.exchange_code(code)
        github_user, email, installations = (
            await service.fetch_github_identity(
                token_set.access_token
            )
        )
    except httpx.HTTPError as exc:
        raise auth_error(
            status_code=502,
            code="GITHUB_OAUTH_FAILED",
            message="GitHub login could not be completed.",
        ) from exc

    installation_service = InstallationService()
    if state_record.purpose in {
        "installation_verification",
        "user_authorization",
    }:
        if (
            auth is None
            or state_record.user_id != auth.user.id
            or int(github_user["id"])
            != auth.user.github_user_id
            or (
                state_record.purpose
                == "installation_verification"
                and state_record.github_installation_id
                is None
            )
        ):
            user_authorization = (
                state_record.purpose
                == "user_authorization"
            )
            raise auth_error(
                status_code=403,
                code=(
                    "GITHUB_USER_AUTHORIZATION_MISMATCH"
                    if user_authorization
                    else "GITHUB_INSTALLATION_NOT_AUTHORIZED"
                ),
                message=(
                    "The GitHub authorization does not match "
                    "the signed-in account."
                    if user_authorization
                    else (
                        "The GitHub installation does not belong to "
                        "the signed-in account."
                    )
                ),
            )
        await service.upsert_user(
            github_user=github_user,
            email=email,
            db=db,
        )
        await GitHubUserTokenService().store(
            user_id=auth.user.id,
            token_set=token_set,
            db=db,
        )
        if state_record.purpose == "user_authorization":
            return RedirectResponse(
                f"{settings.frontend_url.rstrip('/')}"
                f"{state_record.redirect_path}"
                "?github=attribution-connected"
            )
        matching_payload = next(
            (
                item
                for item in installations
                if int(item["id"])
                == state_record.github_installation_id
            ),
            None,
        )
        if matching_payload is None:
            raise auth_error(
                status_code=403,
                code="GITHUB_INSTALLATION_NOT_AUTHORIZED",
                message=(
                    "GitHub did not confirm access to this installation."
                ),
            )
        installation = (
            await installation_service.upsert_installation(
                user_id=auth.user.id,
                payload=matching_payload,
                db=db,
                commit=True,
            )
        )
        await installation_service.sync_repositories(
            installation=installation,
            db=db,
        )
        return RedirectResponse(
            f"{settings.frontend_url.rstrip('/')}"
            f"{state_record.redirect_path}?github=connected"
        )

    user = await service.upsert_user(
        github_user=github_user,
        email=email,
        db=db,
    )
    await GitHubUserTokenService().store(
        user_id=user.id,
        token_set=token_set,
        db=db,
    )
    installation_records = (
        await installation_service.sync_installations(
            user_id=user.id,
            installations=installations,
            db=db,
        )
    )
    for installation in installation_records:
        if installation.status != "active":
            continue
        try:
            await installation_service.sync_repositories(
                installation=installation,
                db=db,
            )
        except HTTPException:
            # Login remains available when one installation is temporarily
            # unavailable; its persisted status drives a recoverable UI error.
            continue
    _, token, csrf_token = await service.create_session(
        user_id=user.id,
        db=db,
    )

    response = RedirectResponse(
        f"{settings.frontend_url.rstrip('/')}"
        f"{state_record.redirect_path}"
    )
    set_auth_cookies(
        response=response,
        session_token=token,
        csrf_token=csrf_token,
    )
    return response


# Purpose: Handle current user for the authentication workflow.
@router.get(
    "/me",
    response_model=CurrentUserResponse,
)
async def current_user(
    user: User = Depends(require_current_user),
):
    return serialize_user(user)


# Purpose: Handle github user authorization for the authentication workflow.
@router.get(
    "/github/user-authorization",
    response_model=GitHubUserAuthorizationResponse,
)
async def github_user_authorization(
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    status = await GitHubUserTokenService().status(
        user_id=user.id,
        db=db,
    )
    return GitHubUserAuthorizationResponse(
        connected=status.connected,
        status=status.status,
        attributed_login=user.github_login,
        access_token_expires_at=(
            status.access_token_expires_at
        ),
        refresh_token_expires_at=(
            status.refresh_token_expires_at
        ),
    )


# Purpose: Handle github user authorization setup for the authentication workflow.
@router.get(
    "/github/user-authorization/setup",
    response_model=GitHubSetupResponse,
)
async def github_user_authorization_setup(
    redirect_to: str = Query(default="/settings"),
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    state = await AuthService().create_oauth_state(
        db=db,
        purpose="user_authorization",
        user_id=user.id,
        redirect_path=redirect_to,
    )
    return GitHubSetupResponse(
        url=AuthService().github_login_url(state)
    )


# Purpose: Handle the logout step of the authentication flow.
@router.post(
    "/logout",
    response_model=LogoutResponse,
)
async def logout(
    response: Response,
    context: AuthContext = Depends(require_auth_context),
    _user: User = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    await AuthService().revoke_session(
        session=context.session,
        db=db,
    )
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        domain=settings.cookie_domain,
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        domain=settings.cookie_domain,
    )
    return LogoutResponse(logged_out=True)


# Purpose: Handle github installation setup for the authentication workflow.
@router.get(
    "/github/installations/setup",
    response_model=GitHubSetupResponse,
)
async def github_installation_setup(
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    missing_settings = missing_github_app_settings()
    if missing_settings:
        raise auth_error(
            status_code=503,
            code="GITHUB_APP_NOT_CONFIGURED",
            message=(
                "Complete the RepoPilot GitHub App configuration "
                "before connecting repositories."
            ),
            details={
                "missing_settings": missing_settings,
            },
        )
    try:
        GitHubAppClient().app_jwt()
    except GitHubAppConfigurationError as exc:
        raise auth_error(
            status_code=503,
            code="GITHUB_APP_NOT_CONFIGURED",
            message=(
                "The RepoPilot GitHub App private key is invalid."
            ),
            details={
                "reason": str(exc),
            },
        ) from exc
    state = await AuthService().create_oauth_state(
        db=db,
        purpose="installation",
        user_id=user.id,
        redirect_path="/settings",
    )
    query = urlencode({"state": state})
    return GitHubSetupResponse(
        url=(
            f"https://github.com/apps/{settings.github_app_slug}"
            f"/installations/new?{query}"
        )
    )


# Purpose: Handle github installation callback for the authentication workflow.
@router.get("/github/installations/callback")
async def github_installation_callback(
    state: str,
    installation_id: int | None = None,
    setup_action: str | None = None,
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    state_record = await AuthService().consume_oauth_state(
        state=state,
        purpose="installation",
        user_id=user.id,
        db=db,
    )
    if (
        installation_id is None
        or setup_action == "request"
    ):
        return RedirectResponse(
            f"{settings.frontend_url.rstrip('/')}"
            f"{state_record.redirect_path}"
            "?github=approval-required"
        )
    verification_state = await AuthService().create_oauth_state(
        db=db,
        purpose="installation_verification",
        user_id=user.id,
        redirect_path=state_record.redirect_path,
        github_installation_id=installation_id,
    )
    return RedirectResponse(
        AuthService().github_login_url(verification_state)
    )


# Purpose: Set auth cookies for the authentication workflow.
def set_auth_cookies(
    *,
    response: Response,
    session_token: str,
    csrf_token: str,
) -> None:
    max_age = settings.session_expiry_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=max_age,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )


# Purpose: Serialize user for the authentication workflow.
def serialize_user(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=str(user.id),
        github_user_id=user.github_user_id,
        github_login=user.github_login,
        github_name=user.github_name,
        github_avatar_url=user.github_avatar_url,
        github_email=user.github_email,
    )
