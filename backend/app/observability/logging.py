import logging
from typing import Any

from app.observability.correlation import (
    get_correlation_id,
    get_request_id,
)
from app.observability.redaction import (
    bounded_metadata,
)


logger = logging.getLogger(
    "repopilot.task"
)


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

