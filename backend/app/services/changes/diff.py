# Module purpose: Implement diff behavior for the change-set domain.

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.services.changes.git import (
    get_changed_files,
    get_file_at_head,
    get_git_diff,
    get_numstat,
    get_untracked_files,
)
from app.services.chunking.chunker import (
    resolve_safe_repository_file,
)


# Purpose: Encapsulate changed file metadata behavior for the change-set domain.
@dataclass(frozen=True)
class ChangedFileMetadata:
    path: str
    before_sha256: str
    after_sha256: str
    lines_added: int
    lines_deleted: int


# Purpose: Encapsulate diff summary behavior for the change-set domain.
@dataclass(frozen=True)
class DiffSummary:
    diff: str
    files: list[ChangedFileMetadata]
    lines_added: int
    lines_deleted: int


# Purpose: Handle sha256 bytes for the change-set workflow.
def sha256_bytes(
    content: bytes,
) -> str:
    return hashlib.sha256(content).hexdigest()


# Purpose: Summarize diff for the change-set workflow.
def summarize_diff(
    repository_path: Path,
) -> DiffSummary:
    changed_files = get_changed_files(
        repository_path
    )
    numstat = get_numstat(
        repository_path
    )
    untracked_files = set(
        get_untracked_files(
            repository_path
        )
    )
    files: list[ChangedFileMetadata] = []

    for path in changed_files:
        before_content = (
            b""
            if path in untracked_files
            else get_file_at_head(
                repository_path,
                path,
            )
        )
        after_content = resolve_safe_repository_file(
            repository_path,
            path,
        ).read_bytes()
        added, deleted = numstat.get(
            path,
            (
                0,
                0,
            ),
        )
        files.append(
            ChangedFileMetadata(
                path=path,
                before_sha256=sha256_bytes(
                    before_content
                ),
                after_sha256=sha256_bytes(
                    after_content
                ),
                lines_added=added,
                lines_deleted=deleted,
            )
        )

    return DiffSummary(
        diff=get_git_diff(
            repository_path
        ),
        files=files,
        lines_added=sum(
            file.lines_added
            for file in files
        ),
        lines_deleted=sum(
            file.lines_deleted
            for file in files
        ),
    )
