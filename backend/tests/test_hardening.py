import asyncio

import httpx
import pytest

from app.services.hardening.limits import (
    StartupConfigurationError,
    validate_safe_root,
)
from app.services.hardening.rate_limit import (
    InMemoryRateLimiter,
)
from app.services.hardening.retries import (
    ProviderFailureCategory,
    classify_provider_failure,
    retry_async,
)


def test_rate_limiter_returns_retry_after():
    limiter = InMemoryRateLimiter()

    assert limiter.check(
        key="ip:test",
        operation="planning",
        limit=2,
        window_seconds=60,
        now=1.0,
    ).allowed
    assert limiter.check(
        key="ip:test",
        operation="planning",
        limit=2,
        window_seconds=60,
        now=2.0,
    ).allowed
    decision = limiter.check(
        key="ip:test",
        operation="planning",
        limit=2,
        window_seconds=60,
        now=3.0,
    )

    assert decision.allowed is False
    assert decision.retry_after_seconds == 58


def test_provider_failure_classification_for_rate_limit():
    request = httpx.Request(
        "GET",
        "https://api.github.com/rate-limit",
    )
    response = httpx.Response(
        429,
        request=request,
    )
    failure = classify_provider_failure(
        httpx.HTTPStatusError(
            "rate limited",
            request=request,
            response=response,
        )
    )

    assert failure.category == ProviderFailureCategory.RATE_LIMIT
    assert failure.retryable is True


def test_retry_async_retries_transient_failure_without_real_sleep():
    calls = 0
    sleeps: list[float] = []

    async def operation():
        nonlocal calls
        calls += 1

        if calls == 1:
            raise TimeoutError()

        return "ok"

    async def sleeper(delay: float):
        sleeps.append(delay)

    result = asyncio.run(
        retry_async(
            operation,
            sleeper=sleeper,
        )
    )

    assert result == "ok"
    assert calls == 2
    assert sleeps


def test_unsafe_root_configuration_is_rejected():
    with pytest.raises(
        StartupConfigurationError
    ):
        validate_safe_root(
            __import__("pathlib").Path("/"),
            field_name="SANDBOX_ROOT",
        )
