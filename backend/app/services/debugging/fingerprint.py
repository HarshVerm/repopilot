import hashlib
import re

from app.db.models.execution_run import (
    ExecutionRun,
)
from app.services.debugging.failure_classifier import (
    FailureClassification,
)


IMPORTANT_MARKERS = (
    "error",
    "failed",
    "failure",
    "expected",
    "received",
    "traceback",
    "assert",
    "exception",
)


def sha256_text(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def diff_hash(
    diff: str | None,
) -> str:
    normalized = (
        diff or ""
    ).replace(
        "\r\n",
        "\n",
    )

    return sha256_text(
        normalized.strip()
    )


def failure_fingerprint(
    *,
    execution_run: ExecutionRun,
    classification: FailureClassification,
) -> str:
    result = classification.failed_result or {}
    text = "\n".join(
        [
            classification.category,
            str(result.get("command_type") or ""),
            str(result.get("exit_code") or ""),
            normalize_failure_text(
                str(result.get("stdout") or "")
                + "\n"
                + str(result.get("stderr") or "")
            ),
        ]
    )

    return sha256_text(text)


def normalize_failure_text(
    text: str,
) -> str:
    lines = [
        normalize_line(line)
        for line in text.splitlines()
    ]
    lines = [
        line
        for line in lines
        if line
    ]
    important = [
        line
        for line in lines
        if any(
            marker in line
            for marker in IMPORTANT_MARKERS
        )
    ]

    selected = (
        important
        if important
        else lines[-20:]
    )

    return "\n".join(
        selected[-40:]
    )


def normalize_line(
    line: str,
) -> str:
    line = line.strip().lower()
    line = re.sub(
        r"0x[0-9a-f]+",
        "0xADDR",
        line,
    )
    line = re.sub(
        r"\d{4}-\d{2}-\d{2}[t ][0-9:.+-]+",
        "TIMESTAMP",
        line,
    )
    line = re.sub(
        r"\s+",
        " ",
        line,
    )

    return line
