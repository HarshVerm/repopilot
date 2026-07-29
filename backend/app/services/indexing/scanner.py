import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.indexing.languages import detect_language


MAX_FILE_SIZE = settings.max_repository_file_size

IGNORED_DIRECTORIES = {
    ".git",
    ".next",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "vendor",
}


@dataclass
class SourceFile:
    relative_path: str
    absolute_path: Path
    language: str
    size_bytes: int


class RepositoryLimitError(RuntimeError):
    pass


def calculate_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def is_relative_to(
    path: Path,
    parent: Path,
) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False

    return True


def has_ignored_directory(
    relative_path: Path,
) -> bool:
    return any(
        part in IGNORED_DIRECTORIES
        for part in relative_path.parts[:-1]
    )


def scan_repository(
    repository_path: Path,
) -> list[SourceFile]:
    repo_root = repository_path.resolve()

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            "ls-files",
            "-z",
        ],
        capture_output=True,
        check=True,
    )

    relative_paths = (
        result.stdout
        .decode("utf-8", errors="ignore")
        .split("\0")
    )

    files: list[SourceFile] = []
    tracked_file_count = 0
    tracked_total_bytes = 0

    for relative_path in relative_paths:

        if not relative_path:
            continue

        tracked_file_count += 1

        if tracked_file_count > settings.max_repository_files:
            raise RepositoryLimitError(
                "repository file count exceeds configured limit"
            )

        relative_file_path = Path(relative_path)

        if (
            relative_file_path.is_absolute()
            or ".." in relative_file_path.parts
            or has_ignored_directory(relative_file_path)
        ):
            continue

        absolute_path = (
            repo_root / relative_file_path
        )

        if absolute_path.is_symlink():
            continue

        try:
            resolved_path = absolute_path.resolve(strict=True)
        except OSError:
            continue

        if not is_relative_to(
            resolved_path,
            repo_root,
        ):
            continue

        if not resolved_path.is_file():
            continue

        size = resolved_path.stat().st_size
        tracked_total_bytes += size

        if tracked_total_bytes > settings.max_repository_bytes:
            raise RepositoryLimitError(
                "repository byte size exceeds configured limit"
            )

        language = detect_language(
            relative_file_path
        )

        if not language:
            continue

        if size > MAX_FILE_SIZE:
            raise RepositoryLimitError(
                "source file size exceeds configured limit"
            )

        # Avoid generated/minified JS
        if resolved_path.name.endswith(
            ".min.js"
        ):
            continue

        files.append(
            SourceFile(
                relative_path=relative_file_path.as_posix(),
                absolute_path=resolved_path,
                language=language,
                size_bytes=size,
            )
        )

    return files
