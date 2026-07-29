import json
import logging
import sys

from app.observability.logging import (
    TaskLogFormatter,
)


def test_task_log_formatter_emits_redacted_json_with_traceback():
    record = logging.LogRecord(
        name="repopilot.task",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="planner.validation_failed",
        args=(),
        exc_info=None,
    )
    record.event_type = "planner.validation_failed"
    record.correlation_id = "correlation-1"
    record.request_id = "request-1"
    record.metadata = {
        "task_id": "task-1",
        "access_token": "must-not-appear",
    }

    try:
        raise RuntimeError(
            "Bearer ghp-supersecret1234567890"
        )
    except RuntimeError:
        record.exc_info = sys.exc_info()

    payload = json.loads(
        TaskLogFormatter().format(record)
    )

    assert payload["level"] == "ERROR"
    assert (
        payload["event_type"]
        == "planner.validation_failed"
    )
    assert payload["metadata"]["task_id"] == "task-1"
    assert (
        payload["metadata"]["access_token"]
        == "[REDACTED]"
    )
    assert "supersecret" not in payload["exception"]
    assert "RuntimeError" in payload["exception"]
