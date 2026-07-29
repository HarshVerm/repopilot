from pathlib import Path

from app.core.config import settings
from app.services.chunking.chunker import (
    UnsafeRepositoryPathError,
    resolve_safe_repository_file,
)


class PathPolicyError(ValueError):
    pass


SENSITIVE_FILENAMES = {
    ".env",
}

SENSITIVE_SUFFIXES = {
    ".key",
    ".pem",
}

DEPENDENCY_FILENAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
}


def is_sensitive_path(
    relative_path: Path,
) -> bool:
    for part in relative_path.parts:
        if part == ".git":
            return True

    name = relative_path.name
    lowered_name = name.lower()

    if name in SENSITIVE_FILENAMES:
        return True

    if name.startswith(".env."):
        return True

    if any(
        lowered_name.endswith(suffix)
        for suffix in SENSITIVE_SUFFIXES
    ):
        return True

    if (
        lowered_name.startswith("credentials")
        or lowered_name.startswith("secrets")
    ):
        return True

    return False


def is_dependency_manifest(
    relative_path: Path,
) -> bool:
    return relative_path.name in DEPENDENCY_FILENAMES


def validate_editable_path(
    *,
    repository_path: Path,
    requested_path: str,
    allowed_files: set[str],
    max_file_size: int = settings.max_editable_file_size,
) -> Path:
    if "\x00" in requested_path:
        raise PathPolicyError(
            "Path contains a null byte"
        )

    relative_path = Path(requested_path)

    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or not requested_path.strip()
    ):
        raise PathPolicyError(
            "Path must be a safe repository-relative path"
        )

    normalized_path = relative_path.as_posix()

    if normalized_path not in allowed_files:
        raise PathPolicyError(
            "Path is outside the approved modification scope"
        )

    if is_sensitive_path(relative_path):
        raise PathPolicyError(
            "Sensitive paths cannot be modified"
        )

    if is_dependency_manifest(relative_path):
        raise PathPolicyError(
            "Dependency manifests are protected in Step 6"
        )

    try:
        resolved_path = resolve_safe_repository_file(
            repository_path,
            normalized_path,
        )
    except UnsafeRepositoryPathError as exc:
        raise PathPolicyError(
            "Path is not an editable repository file"
        ) from exc

    size_bytes = resolved_path.stat().st_size

    if size_bytes > max_file_size:
        raise PathPolicyError(
            "File exceeds editable size limit"
        )

    return resolved_path
