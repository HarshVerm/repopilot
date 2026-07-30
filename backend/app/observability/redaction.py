# Module purpose: Implement redaction behavior for the observability domain.

from collections.abc import Mapping
import re
from typing import Any


REDACTED = "[REDACTED]"
MAX_STRING_LENGTH = 2000
MAX_LIST_ITEMS = 50
MAX_DICT_ITEMS = 100
MAX_METADATA_DEPTH = 5

SENSITIVE_KEY_PARTS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "secret",
    "token",
    "private_key",
    "private-key",
    "openai_api_key",
    "github_token",
    "installation_token",
    "access_token",
}

BEARER_TOKEN_RE = re.compile(
    r"Bearer\s+[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)
LONG_SECRET_RE = re.compile(
    r"\b(?:ghp|gho|ghu|ghs|github_pat|sk)-[A-Za-z0-9_\-]{12,}\b"
)


# Purpose: Return whether sensitive key.
def is_sensitive_key(
    key: object,
) -> bool:
    lowered = str(key).lower()
    return any(
        part in lowered
        for part in SENSITIVE_KEY_PARTS
    )


# Purpose: Redact string for the observability workflow.
def redact_string(
    value: str,
) -> str:
    redacted = BEARER_TOKEN_RE.sub(
        REDACTED,
        value,
    )
    redacted = LONG_SECRET_RE.sub(
        REDACTED,
        redacted,
    )

    if len(redacted) > MAX_STRING_LENGTH:
        return (
            redacted[:MAX_STRING_LENGTH]
            + "...[truncated]"
        )

    return redacted


# Purpose: Redact observability for the observability workflow.
def redact(
    value: Any,
    *,
    depth: int = 0,
) -> Any:
    if depth >= MAX_METADATA_DEPTH:
        return "[truncated-depth]"

    if isinstance(
        value,
        str,
    ):
        return redact_string(
            value
        )

    if isinstance(
        value,
        Mapping,
    ):
        items = list(value.items())[
            :MAX_DICT_ITEMS
        ]
        safe: dict[str, Any] = {}

        for key, item in items:
            key_text = str(key)
            if is_sensitive_key(
                key_text
            ):
                safe[key_text] = REDACTED
            else:
                safe[key_text] = redact(
                    item,
                    depth=depth + 1,
                )

        if len(value) > MAX_DICT_ITEMS:
            safe["_truncated_items"] = (
                len(value) - MAX_DICT_ITEMS
            )

        return safe

    if isinstance(
        value,
        (list, tuple, set),
    ):
        items = list(value)
        redacted_items = [
            redact(
                item,
                depth=depth + 1,
            )
            for item in items[:MAX_LIST_ITEMS]
        ]

        if len(items) > MAX_LIST_ITEMS:
            redacted_items.append(
                {
                    "_truncated_items": (
                        len(items) - MAX_LIST_ITEMS
                    )
                }
            )

        return redacted_items

    if value is None or isinstance(
        value,
        (bool, int, float),
    ):
        return value

    return redact_string(
        str(value)
    )


# Purpose: Handle bounded metadata for the observability workflow.
def bounded_metadata(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not metadata:
        return {}

    redacted = redact(
        metadata
    )
    assert isinstance(redacted, dict)
    return redacted

