# Module purpose: Implement logging behavior for the observability domain.

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.observability.correlation import (
    get_correlation_id,
    get_request_id,
)
from app.observability.redaction import (
    bounded_metadata,
    redact_string,
)


logger = logging.getLogger(
    "repopilot.task"
)


class TaskLogFormatter(logging.Formatter):
    """Render task lifecycle logs as safe, searchable JSON lines."""

    # Purpose: Format observability for the observability workflow.
    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event_type": getattr(
                record,
                "event_type",
                record.getMessage(),
            ),
            "correlation_id": getattr(
                record,
                "correlation_id",
                None,
            ),
            "request_id": getattr(
                record,
                "request_id",
                None,
            ),
            "metadata": bounded_metadata(
                getattr(record, "metadata", {})
            ),
        }
        if record.exc_info:
            payload["exception"] = redact_string(
                self.formatException(
                    record.exc_info
                )
            )
        return json.dumps(
            payload,
            sort_keys=True,
            default=str,
        )


def configure_task_logging(
    level: str = "INFO",
) -> None:
    """Ensure task logs are visible even when the root logger has no handler."""

    resolved_level = getattr(
        logging,
        level.upper(),
        logging.INFO,
    )
    logger.setLevel(resolved_level)
    logger.propagate = False

    for handler in logger.handlers:
        if getattr(
            handler,
            "_repopilot_task_handler",
            False,
        ):
            handler.setLevel(resolved_level)
            return

    handler = logging.StreamHandler(
        sys.stdout
    )
    handler.setLevel(resolved_level)
    handler.setFormatter(
        TaskLogFormatter()
    )
    handler._repopilot_task_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)


# Purpose: Log task event for the observability workflow.
def log_task_event(
    event_type: str,
    **fields: Any,
) -> None:
    logger.info(
        event_type,
        extra={
            "event_type": event_type,
            "correlation_id": get_correlation_id(),
            "request_id": get_request_id(),
            "metadata": bounded_metadata(
                fields
            ),
        },
    )


def log_task_failure(
    event_type: str,
    error: BaseException,
    **fields: Any,
) -> None:
    """Log a task failure with its original traceback and redacted metadata."""

    logger.error(
        event_type,
        extra={
            "event_type": event_type,
            "correlation_id": get_correlation_id(),
            "request_id": get_request_id(),
            "metadata": bounded_metadata(
                {
                    **fields,
                    "error_type": error.__class__.__name__,
                    "error_message": str(error),
                }
            ),
        },
        exc_info=(
            error.__class__,
            error,
            error.__traceback__,
        ),
    )
