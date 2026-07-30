# Module purpose: Implement policy behavior for the debugging domain.

from dataclasses import dataclass
from pathlib import Path

from app.agents.coder.service import (
    allowed_files_from_plan,
)
from app.db.models.execution_plan import (
    ExecutionPlan,
)
from app.schemas.debugging import (
    DebuggerOutput,
)
from app.services.changes.git import (
    get_git_status,
    run_git,
)
from app.services.changes.snapshot import (
    parse_status_paths,
    safe_unlink_untracked,
    status_contains_untracked,
)
from app.services.debugging.fingerprint import (
    diff_hash,
)


# Purpose: Signal debug not eligible failures.
class DebugNotEligibleError(ValueError):
    pass


# Purpose: Signal plan revision required failures.
class PlanRevisionRequiredError(ValueError):
    pass


# Purpose: Signal debug patch validation failures.
class DebugPatchValidationError(ValueError):
    pass


# Purpose: Signal debug attempts exceeded failures.
class DebugAttemptsExceededError(ValueError):
    pass


# Purpose: Signal no progress failures.
class NoProgressError(ValueError):
    pass


# Purpose: Signal debugger execution failures.
class DebuggerExecutionError(RuntimeError):
    pass


# Purpose: Encapsulate workspace patch snapshot behavior for the debugging domain.
@dataclass(frozen=True)
class WorkspacePatchSnapshot:
    files: dict[str, bytes]
    diff: str
    diff_hash: str


# Purpose: Handle approved files from plan for the debugging workflow.
def approved_files_from_plan(
    plan: ExecutionPlan,
) -> set[str]:
    return allowed_files_from_plan(
        plan
    )


# Purpose: Validate debugger scope for the debugging workflow.
def validate_debugger_scope(
    *,
    output: DebuggerOutput,
    approved_files: set[str],
) -> None:
    requested = {
        path
        for path in output.files_to_modify
        if path
    }
    unauthorized = requested - approved_files

    if unauthorized:
        raise PlanRevisionRequiredError(
            "Debugger requested files outside approved scope: "
            + ", ".join(
                sorted(unauthorized)
            )
        )


# Purpose: Handle capture patch snapshot for the debugging workflow.
def capture_patch_snapshot(
    repository_path: Path,
) -> WorkspacePatchSnapshot:
    diff = run_git(
        repository_path,
        [
            "diff",
            "--no-ext-diff",
            "--unified=3",
        ],
    )
    paths = [
        path
        for path in run_git(
            repository_path,
            [
                "diff",
                "--name-only",
            ],
        ).splitlines()
        if path
    ]
    files: dict[str, bytes] = {}

    for path in paths:
        target = repository_path / path

        if target.is_file():
            files[path] = target.read_bytes()

    return WorkspacePatchSnapshot(
        files=files,
        diff=diff,
        diff_hash=diff_hash(diff),
    )


# Purpose: Handle restore patch snapshot for the debugging workflow.
def restore_patch_snapshot(
    *,
    repository_path: Path,
    snapshot: WorkspacePatchSnapshot,
) -> None:
    status = get_git_status(
        repository_path
    )
    paths = parse_status_paths(
        status
    )

    tracked_paths = [
        path
        for path in paths
        if not status_contains_untracked(
            status,
            path,
        )
    ]
    untracked_paths = [
        path
        for path in paths
        if status_contains_untracked(
            status,
            path,
        )
    ]

    if tracked_paths:
        run_git(
            repository_path,
            [
                "checkout",
                "--",
                *tracked_paths,
            ],
        )

    for path in untracked_paths:
        safe_unlink_untracked(
            repository_path,
            path,
        )

    for path, content in snapshot.files.items():
        target = repository_path / path
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        target.write_bytes(content)

    restored = capture_patch_snapshot(
        repository_path
    )

    if restored.diff_hash != snapshot.diff_hash:
        raise DebugPatchValidationError(
            "Failed to restore prior ChangeSet patch"
        )
