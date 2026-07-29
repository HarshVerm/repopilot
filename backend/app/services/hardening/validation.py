import json
from typing import Any

from app.core.config import settings


class InputLimitError(ValueError):
    pass


def validate_bounded_text(
    value: str | None,
    *,
    field_name: str,
    max_chars: int,
    allow_blank: bool = False,
) -> str:
    text = (
        value or ""
    )

    if not allow_blank and not text.strip():
        raise InputLimitError(
            f"{field_name} must not be blank"
        )

    if len(text) > max_chars:
        raise InputLimitError(
            f"{field_name} exceeds {max_chars} characters"
        )

    return text


def validate_issue_payload(
    *,
    title: str | None,
    body: str | None,
) -> None:
    validate_bounded_text(
        title,
        field_name="issue title",
        max_chars=settings.max_issue_title_chars,
    )
    validate_bounded_text(
        body,
        field_name="issue body",
        max_chars=settings.max_issue_body_chars,
        allow_blank=True,
    )


def validate_retrieval_request(
    *,
    query: str,
    top_k: int,
) -> None:
    validate_bounded_text(
        query,
        field_name="retrieval query",
        max_chars=settings.retrieval_query_max_chars,
    )

    if top_k < 1 or top_k > settings.retrieval_top_k_max:
        raise InputLimitError(
            f"top_k must be between 1 and {settings.retrieval_top_k_max}"
        )


def validate_task_event_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if metadata is None:
        return None

    encoded = json.dumps(
        metadata,
        sort_keys=True,
        default=str,
    ).encode("utf-8")

    if len(encoded) > settings.max_task_event_metadata_bytes:
        raise InputLimitError(
            "TaskEvent metadata exceeds configured size limit"
        )

    return metadata
