import hashlib


def sha256_text(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def normalize_diff(
    diff: str | None,
) -> str:
    return (
        diff or ""
    ).replace(
        "\r\n",
        "\n",
    ).strip()


def diff_hash(
    diff: str | None,
) -> str:
    return sha256_text(
        normalize_diff(diff)
    )
