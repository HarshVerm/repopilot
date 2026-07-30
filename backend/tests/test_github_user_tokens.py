import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.models.identity import (
    GitHubUserAuthorization,
    User,
)
from app.db.session import AsyncSessionLocal
from app.services.auth.github_tokens import (
    GitHubOAuthTokenSet,
    GitHubTokenCipher,
    GitHubUserAuthorizationRequired,
    GitHubUserTokenService,
)


def test_github_token_cipher_round_trip():
    cipher = GitHubTokenCipher(
        "test-encryption-secret-that-is-long-enough"
    )
    ciphertext = cipher.encrypt("ghu_sensitive-token")

    assert ciphertext != "ghu_sensitive-token"
    assert "ghu_sensitive-token" not in ciphertext
    assert cipher.decrypt(ciphertext) == "ghu_sensitive-token"


def test_github_user_token_is_encrypted_and_refreshed(
    monkeypatch,
):
    requests: list[dict] = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "access_token": "ghu_rotated-token",
                "expires_in": 28_800,
                "refresh_token": "ghr_rotated-token",
                "refresh_token_expires_in": 15_897_600,
                "token_type": "bearer",
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        async def post(
            self,
            url,
            *,
            headers,
            data,
        ):
            requests.append(
                {
                    "url": url,
                    "headers": headers,
                    "data": data,
                }
            )
            return FakeResponse()

    def client_factory(**kwargs):
        assert kwargs["timeout"] == settings.github_timeout_seconds
        return FakeClient()

    monkeypatch.setattr(
        settings,
        "github_app_client_id",
        "Iv1.client",
    )
    monkeypatch.setattr(
        settings,
        "github_app_client_secret",
        "client-secret",
    )
    user_id = uuid.uuid4()
    cipher = GitHubTokenCipher(
        "test-encryption-secret-that-is-long-enough"
    )
    service = GitHubUserTokenService(
        cipher=cipher,
        http_client_factory=client_factory,
    )

    async def run():
        try:
            async with AsyncSessionLocal() as db:
                db.add(
                    User(
                        id=user_id,
                        github_user_id=abs(
                            hash(user_id.hex)
                        ),
                        github_login="token-user",
                    )
                )
                await db.commit()
                authorization = await service.store(
                    user_id=user_id,
                    token_set=GitHubOAuthTokenSet(
                        access_token="ghu_original-token",
                        access_token_expires_at=(
                            datetime.now(UTC)
                            - timedelta(minutes=1)
                        ),
                        refresh_token="ghr_original-token",
                        refresh_token_expires_at=(
                            datetime.now(UTC)
                            + timedelta(days=30)
                        ),
                    ),
                    db=db,
                )
                assert (
                    "ghu_original-token"
                    not in authorization.access_token_ciphertext
                )
                assert (
                    authorization.refresh_token_ciphertext
                    is not None
                )
                assert (
                    "ghr_original-token"
                    not in authorization.refresh_token_ciphertext
                )

                access_token = await service.access_token(
                    user_id=user_id,
                    db=db,
                )
                assert access_token == "ghu_rotated-token"

                refreshed = await db.scalar(
                    select(
                        GitHubUserAuthorization
                    ).where(
                        GitHubUserAuthorization.user_id
                        == user_id
                    )
                )
                assert refreshed is not None
                assert refreshed.last_refreshed_at is not None
                assert (
                    cipher.decrypt(
                        refreshed.access_token_ciphertext
                    )
                    == "ghu_rotated-token"
                )
                assert refreshed.refresh_token_ciphertext
                assert (
                    cipher.decrypt(
                        refreshed.refresh_token_ciphertext
                    )
                    == "ghr_rotated-token"
                )
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(User).where(User.id == user_id)
                )
                await db.commit()

    asyncio.run(run())

    assert len(requests) == 1
    assert requests[0]["data"] == {
        "client_id": "Iv1.client",
        "client_secret": "client-secret",
        "grant_type": "refresh_token",
        "refresh_token": "ghr_original-token",
    }


def test_missing_github_user_authorization_requires_reconnect():
    service = GitHubUserTokenService(
        cipher=GitHubTokenCipher(
            "test-encryption-secret-that-is-long-enough"
        )
    )
    user_id = uuid.uuid4()

    async def run():
        async with AsyncSessionLocal() as db:
            with pytest.raises(
                GitHubUserAuthorizationRequired
            ):
                await service.access_token(
                    user_id=user_id,
                    db=db,
                )

    asyncio.run(run())
