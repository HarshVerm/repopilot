import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import settings


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None


class RateLimitExceeded(RuntimeError):
    def __init__(
        self,
        *,
        retry_after_seconds: int,
    ) -> None:
        super().__init__(
            "Rate limit exceeded"
        )
        self.retry_after_seconds = retry_after_seconds


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[
            tuple[str, str],
            list[float],
        ] = {}

    def check(
        self,
        *,
        key: str,
        operation: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> RateLimitDecision:
        current = now or time.monotonic()
        bucket_key = (
            key,
            operation,
        )
        cutoff = current - window_seconds
        timestamps = [
            value
            for value in self._buckets.get(
                bucket_key,
                [],
            )
            if value > cutoff
        ]

        if len(timestamps) >= limit:
            retry_after = max(
                1,
                int(
                    window_seconds
                    - (current - min(timestamps))
                ),
            )
            self._buckets[bucket_key] = timestamps
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry_after,
            )

        timestamps.append(
            current
        )
        self._buckets[bucket_key] = timestamps
        return RateLimitDecision(
            allowed=True,
            retry_after_seconds=None,
        )

    def reset(self) -> None:
        self._buckets.clear()


RATE_LIMITS_BY_OPERATION = {
    "task_create": settings.rate_limit_task_create,
    "planning": settings.rate_limit_planning,
    "coding": settings.rate_limit_coding,
    "sandbox": settings.rate_limit_sandbox,
    "debug": settings.rate_limit_debug,
    "publication": settings.rate_limit_publication,
    "evaluation_launch": settings.rate_limit_evaluation_launch,
}


rate_limiter = InMemoryRateLimiter()


def enforce_rate_limit(
    operation: str,
):
    async def dependency(
        request: Request,
    ) -> None:
        key = rate_limit_key(
            request
        )
        limit = RATE_LIMITS_BY_OPERATION[
            operation
        ]
        decision = rate_limiter.check(
            key=key,
            operation=operation,
            limit=limit,
            window_seconds=(
                settings.rate_limit_window_seconds
            ),
        )

        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many expensive RepoPilot operations. Retry later.",
                headers={
                    "Retry-After": str(
                        decision.retry_after_seconds
                        or settings.rate_limit_window_seconds
                    )
                },
            )

    return dependency


def rate_limit_key(
    request: Request,
) -> str:
    authorization = request.headers.get(
        "Authorization"
    )

    if authorization:
        return "auth:" + str(
            hash(authorization)
        )

    if request.client is not None:
        return "ip:" + request.client.host

    return "global"
