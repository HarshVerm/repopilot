# Module purpose: Implement hashing behavior for the change-set domain.

import hashlib


# Purpose: Handle sha256 text for the change-set workflow.
def sha256_text(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# Purpose: Normalize diff for the change-set workflow.
def normalize_diff(
    diff: str | None,
) -> str:
    return (
        diff or ""
    ).replace(
        "\r\n",
        "\n",
    ).strip()


# Purpose: Handle diff hash for the change-set workflow.
def diff_hash(
    diff: str | None,
) -> str:
    return sha256_text(
        normalize_diff(diff)
    )
