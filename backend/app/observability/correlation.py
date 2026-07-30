# Module purpose: Implement correlation behavior for the observability domain.

import contextvars
import re
import uuid
from contextlib import contextmanager
from collections.abc import Iterator


_CORRELATION_ID: contextvars.ContextVar[str | None] = (
    contextvars.ContextVar(
        "correlation_id",
        default=None,
    )
)
_REQUEST_ID: contextvars.ContextVar[str | None] = (
    contextvars.ContextVar(
        "request_id",
        default=None,
    )
)

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")


# Purpose: Generate correlation id for the observability workflow.
def generate_correlation_id() -> str:
    return str(uuid.uuid4())


# Purpose: Validate or generate correlation id for the observability workflow.
def validate_or_generate_correlation_id(
    value: str | None,
) -> str:
    if value and SAFE_ID_RE.match(value):
        return value

    return generate_correlation_id()


# Purpose: Return correlation id for the observability workflow.
def get_correlation_id() -> str | None:
    return _CORRELATION_ID.get()


# Purpose: Return request id for the observability workflow.
def get_request_id() -> str | None:
    return _REQUEST_ID.get()


# Purpose: Handle correlation context for the observability workflow.
@contextmanager
def correlation_context(
    *,
    correlation_id: str | None,
    request_id: str | None = None,
) -> Iterator[str]:
    resolved = validate_or_generate_correlation_id(
        correlation_id
    )
    request = (
        request_id
        if request_id and SAFE_ID_RE.match(request_id)
        else resolved
    )
    correlation_token = _CORRELATION_ID.set(
        resolved
    )
    request_token = _REQUEST_ID.set(
        request
    )

    try:
        yield resolved
    finally:
        _CORRELATION_ID.reset(
            correlation_token
        )
        _REQUEST_ID.reset(
            request_token
        )

