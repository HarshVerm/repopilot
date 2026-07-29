import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

import httpx

from app.core.config import settings


T = TypeVar("T")


class ProviderFailureCategory(StrEnum):
    RATE_LIMIT = "provider_rate_limit"
    TIMEOUT = "provider_timeout"
    SERVER_ERROR = "provider_server_error"
    AUTH_ERROR = "provider_auth_error"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    CLIENT_ERROR = "provider_client_error"
    UNKNOWN = "provider_unknown_error"


@dataclass(frozen=True)
class ProviderFailure:
    category: ProviderFailureCategory
    retryable: bool
    status_code: int | None = None


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = settings.provider_max_retries
    initial_backoff_seconds: float = (
        settings.provider_retry_initial_backoff_seconds
    )
    max_backoff_seconds: float = (
        settings.provider_retry_max_backoff_seconds
    )
    jitter_ratio: float = 0.20


RETRYABLE_HTTP_STATUSES = {
    429,
    502,
    503,
    504,
}


def classify_provider_failure(
    exc: Exception,
) -> ProviderFailure:
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            TimeoutError,
        ),
    ):
        return ProviderFailure(
            ProviderFailureCategory.TIMEOUT,
            retryable=True,
        )

    if isinstance(
        exc,
        httpx.HTTPStatusError,
    ):
        status_code = exc.response.status_code

        if status_code == 429:
            return ProviderFailure(
                ProviderFailureCategory.RATE_LIMIT,
                retryable=True,
                status_code=status_code,
            )
        if status_code in {
            401,
            403,
        }:
            return ProviderFailure(
                ProviderFailureCategory.AUTH_ERROR,
                retryable=False,
                status_code=status_code,
            )
        if status_code in RETRYABLE_HTTP_STATUSES:
            return ProviderFailure(
                ProviderFailureCategory.SERVER_ERROR,
                retryable=True,
                status_code=status_code,
            )
        if 400 <= status_code < 500:
            return ProviderFailure(
                ProviderFailureCategory.CLIENT_ERROR,
                retryable=False,
                status_code=status_code,
            )

    class_name = exc.__class__.__name__.lower()

    if "ratelimit" in class_name or "rate_limit" in class_name:
        return ProviderFailure(
            ProviderFailureCategory.RATE_LIMIT,
            retryable=True,
        )
    if "timeout" in class_name:
        return ProviderFailure(
            ProviderFailureCategory.TIMEOUT,
            retryable=True,
        )
    if "authentication" in class_name or "permission" in class_name:
        return ProviderFailure(
            ProviderFailureCategory.AUTH_ERROR,
            retryable=False,
        )
    if "validation" in class_name:
        return ProviderFailure(
            ProviderFailureCategory.INVALID_MODEL_OUTPUT,
            retryable=False,
        )

    return ProviderFailure(
        ProviderFailureCategory.UNKNOWN,
        retryable=False,
    )


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> T:
    retry_policy = policy or RetryPolicy()
    random_source = rng or random.Random()
    attempt = 0
    last_error: Exception | None = None

    while attempt < retry_policy.max_attempts:
        attempt += 1

        try:
            return await operation()
        except Exception as exc:
            last_error = exc
            failure = classify_provider_failure(
                exc
            )

            if (
                not failure.retryable
                or attempt >= retry_policy.max_attempts
            ):
                raise

            await sleeper(
                retry_delay_seconds(
                    attempt=attempt,
                    policy=retry_policy,
                    rng=random_source,
                )
            )

    assert last_error is not None
    raise last_error


def retry_delay_seconds(
    *,
    attempt: int,
    policy: RetryPolicy,
    rng: random.Random,
) -> float:
    base = min(
        policy.initial_backoff_seconds
        * (2 ** max(attempt - 1, 0)),
        policy.max_backoff_seconds,
    )
    jitter = base * policy.jitter_ratio
    return max(
        0.0,
        base + rng.uniform(
            -jitter,
            jitter,
        ),
    )
