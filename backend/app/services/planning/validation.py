from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.code_index import RepositoryFile
from app.schemas.planning import (
    ImplementationStep,
    PlannedFile,
    PlannerOutput,
    SourceReference,
)
from app.services.chunking.chunker import (
    UnsafeRepositoryPathError,
    resolve_safe_repository_file,
)
from app.services.changes.policy import (
    PathPolicyError,
    validate_creatable_path,
)


class PlanValidationError(ValueError):
    pass


def validate_relative_plan_path(
    path: str,
) -> None:
    parsed_path = Path(path)

    if (
        not path.strip()
        or parsed_path.is_absolute()
        or ".." in parsed_path.parts
    ):
        raise PlanValidationError(
            f"Invalid repository-relative path: {path}"
        )


async def load_workspace_file_paths(
    db: AsyncSession,
    *,
    workspace_id: str,
) -> set[str]:
    result = await db.execute(
        select(RepositoryFile.file_path).where(
            RepositoryFile.workspace_id
            == workspace_id
        )
    )

    return {
        row.file_path
        for row in result.all()
    }


def count_file_lines(
    repository_path: Path,
    file_path: str,
) -> int:
    try:
        resolved_path = resolve_safe_repository_file(
            repository_path,
            file_path,
        )
    except UnsafeRepositoryPathError as exc:
        raise PlanValidationError(
            f"Unsafe source reference path: {file_path}"
        ) from exc

    content = resolved_path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    return max(
        1,
        len(content.splitlines()),
    )


def validate_file_exists(
    path: str,
    existing_paths: set[str],
) -> None:
    validate_relative_plan_path(path)

    if path not in existing_paths:
        raise PlanValidationError(
            f"Planner referenced unknown file: {path}"
        )


def validate_source_reference(
    reference: SourceReference,
    *,
    existing_paths: set[str],
    repository_path: Path,
) -> None:
    validate_file_exists(
        reference.file_path,
        existing_paths,
    )

    if (
        reference.start_line is None
        and reference.end_line is not None
    ):
        raise PlanValidationError(
            "Source reference end_line requires start_line"
        )

    if (
        reference.start_line is not None
        and reference.end_line is not None
        and reference.end_line < reference.start_line
    ):
        raise PlanValidationError(
            "Source reference end_line must be greater than or equal to start_line"
        )

    if (
        reference.start_line is not None
        or reference.end_line is not None
    ):
        line_count = count_file_lines(
            repository_path,
            reference.file_path,
        )

        if (
            reference.start_line is not None
            and reference.start_line > line_count
        ):
            raise PlanValidationError(
                "Source reference line range exceeds file length: "
                f"{reference.file_path}"
            )

    if reference.end_line is not None:
        if reference.end_line > line_count:
            raise PlanValidationError(
                "Source reference line range exceeds file length: "
                f"{reference.file_path}"
            )


def validate_planned_file(
    planned_file: PlannedFile,
    *,
    existing_paths: set[str],
    repository_path: Path,
) -> None:
    validate_file_exists(
        planned_file.path,
        existing_paths,
    )

    for reference in planned_file.references:
        validate_source_reference(
            reference,
            existing_paths=existing_paths,
            repository_path=repository_path,
        )


def validate_planned_modification(
    planned_file: PlannedFile,
    *,
    existing_paths: set[str],
    repository_path: Path,
) -> None:
    if planned_file.change_type == "modify":
        validate_planned_file(
            planned_file,
            existing_paths=existing_paths,
            repository_path=repository_path,
        )
        return

    validate_relative_plan_path(
        planned_file.path
    )

    if planned_file.path in existing_paths:
        raise PlanValidationError(
            "Planner marked an existing file for creation: "
            f"{planned_file.path}"
        )

    if planned_file.references:
        raise PlanValidationError(
            "A new file cannot contain source references: "
            f"{planned_file.path}"
        )

    try:
        validate_creatable_path(
            repository_path=repository_path,
            requested_path=planned_file.path,
            allowed_files={
                planned_file.path
            },
        )
    except (OSError, PathPolicyError) as exc:
        raise PlanValidationError(
            "Planner proposed an unsafe new file: "
            f"{planned_file.path} ({exc})"
        ) from exc


def validate_implementation_step(
    step: ImplementationStep,
    *,
    allowed_paths: set[str],
) -> None:
    for file_path in step.files:
        validate_file_exists(
            file_path,
            allowed_paths,
        )


async def validate_planner_output(
    *,
    output: PlannerOutput,
    workspace_id: str,
    repository_path: Path,
    db: AsyncSession,
) -> None:
    existing_paths = await load_workspace_file_paths(
        db,
        workspace_id=workspace_id,
    )

    if (
        output.needs_more_context
        and not output.missing_context
    ):
        raise PlanValidationError(
            "missing_context is required when needs_more_context is true"
        )

    if (
        output.needs_more_context
        and output.confidence > 0.6
    ):
        raise PlanValidationError(
            "confidence must remain conservative when more context is needed"
        )

    modification_paths = [
        planned_file.path
        for planned_file in output.files_to_modify
    ]
    if len(modification_paths) != len(
        set(modification_paths)
    ):
        raise PlanValidationError(
            "files_to_modify contains duplicate paths"
        )

    created_paths = {
        planned_file.path
        for planned_file in output.files_to_modify
        if planned_file.change_type == "create"
    }

    if not existing_paths and not created_paths:
        raise PlanValidationError(
            "Workspace has no indexed repository files and the plan "
            "does not explicitly create a new file"
        )

    for planned_file in output.files_to_inspect:
        if planned_file.change_type != "modify":
            raise PlanValidationError(
                "files_to_inspect cannot mark files for creation"
            )
        validate_planned_file(
            planned_file,
            existing_paths=existing_paths,
            repository_path=repository_path,
        )

    for planned_file in output.files_to_modify:
        validate_planned_modification(
            planned_file,
            existing_paths=existing_paths,
            repository_path=repository_path,
        )

    for step in output.implementation_steps:
        validate_implementation_step(
            step,
            allowed_paths=(
                existing_paths
                | created_paths
            ),
        )
