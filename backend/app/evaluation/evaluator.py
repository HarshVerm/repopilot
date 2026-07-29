import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.execution_plan import ExecutionPlan
from app.db.models.final_review import FinalReview
from app.services.planning.service import PlannerService
from app.services.reviews.service import ReviewService
from app.services.sandbox.docker import (
    DockerSandbox,
    SandboxHandle,
)
from app.services.sandbox.results import (
    ExecutionCommand,
    overall_status,
)
from app.services.tasks.service import (
    TaskService,
)


class EvaluationModeError(PermissionError):
    pass


@dataclass(frozen=True)
class EvaluationContext:
    evaluation_run_id: str
    evaluation_task_id: str
    enabled: bool


class EvalApprovalPolicy:
    def ensure_enabled(
        self,
        context: EvaluationContext,
    ) -> None:
        if not settings.evaluation_mode or not context.enabled:
            raise EvaluationModeError(
                "evaluation auto-approval requires EVALUATION_MODE=true and an explicit evaluation context"
            )

    async def approve_plan(
        self,
        *,
        plan: ExecutionPlan,
        context: EvaluationContext,
        db: AsyncSession,
    ) -> ExecutionPlan:
        self.ensure_enabled(
            context
        )
        approved = await PlannerService().approve_plan(
            plan_id=plan.id,
            db=db,
        )

        if approved.task_id is not None:
            await TaskService().record_event(
                task_id=approved.task_id,
                event_type="evaluation.plan_auto_approved",
                db=db,
                metadata={
                    "evaluation_run_id": context.evaluation_run_id,
                    "evaluation_task_id": context.evaluation_task_id,
                    "automated_approval": True,
                },
                commit=True,
            )

        return approved

    async def approve_review(
        self,
        *,
        review: FinalReview,
        repository_path: Path,
        context: EvaluationContext,
        db: AsyncSession,
    ) -> FinalReview:
        self.ensure_enabled(
            context
        )
        approved = await ReviewService().approve_review(
            review_id=review.id,
            repository_path=repository_path,
            db=db,
        )

        if approved.task_id is not None:
            await TaskService().record_event(
                task_id=approved.task_id,
                event_type="evaluation.review_auto_approved",
                db=db,
                metadata={
                    "evaluation_run_id": context.evaluation_run_id,
                    "evaluation_task_id": context.evaluation_task_id,
                    "automated_approval": True,
                },
                commit=True,
            )

        return approved


class HiddenTestFile(BaseModel):
    path: str
    content: str


class HiddenTestCommand(BaseModel):
    name: str
    command_type: str = "test"
    executable: str
    args: list[str]
    timeout_seconds: int = 120
    network_enabled: bool = False
    runtime: str = "python"


class HiddenTestManifest(BaseModel):
    files: list[HiddenTestFile]
    commands: list[HiddenTestCommand]


class HiddenTestResult(BaseModel):
    status: str
    results: list[dict]


class HiddenTestRunner:
    def __init__(
        self,
        *,
        sandbox: DockerSandbox | None = None,
    ) -> None:
        self.sandbox = sandbox or DockerSandbox()

    def run(
        self,
        *,
        repository_path: Path,
        hidden_test_path: Path,
    ) -> HiddenTestResult:
        manifest = load_hidden_manifest(
            hidden_test_path
        )
        handle: SandboxHandle | None = None

        try:
            handle = self.sandbox.prepare(
                execution_run_id=uuid.uuid4(),
                source_repository=repository_path,
            )
            write_hidden_files(
                handle.repository_path,
                manifest.files,
            )
            command_results = [
                self.sandbox.execute(
                    handle=handle,
                    command=execution_command(
                        command
                    ),
                )
                for command in manifest.commands
            ]
            return HiddenTestResult(
                status=overall_status(
                    command_results
                ),
                results=[
                    result.to_json()
                    for result in command_results
                ],
            )
        finally:
            self.sandbox.cleanup(
                handle
            )


def load_hidden_manifest(
    hidden_test_path: Path,
) -> HiddenTestManifest:
    with hidden_test_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return HiddenTestManifest.model_validate(
            json.load(file)
        )


def write_hidden_files(
    repository_path: Path,
    files: list[HiddenTestFile],
) -> None:
    root = repository_path.resolve()

    for file in files:
        relative = Path(
            file.path
        )

        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not file.path.strip()
        ):
            raise EvaluationModeError(
                "hidden test file path is unsafe"
            )

        destination = (
            root
            / relative
        )
        resolved = destination.resolve(
            strict=False
        )

        try:
            resolved.relative_to(
                root
            )
        except ValueError as exc:
            raise EvaluationModeError(
                "hidden test file escapes sandbox"
            ) from exc

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        destination.write_text(
            file.content,
            encoding="utf-8",
        )


def execution_command(
    command: HiddenTestCommand,
) -> ExecutionCommand:
    return ExecutionCommand(
        name=command.name,
        command_type=command.command_type,
        executable=command.executable,
        args=hidden_command_args(
            command
        ),
        timeout_seconds=command.timeout_seconds,
        network_enabled=command.network_enabled,
        runtime=command.runtime,
    )


def hidden_command_args(
    command: HiddenTestCommand,
) -> list[str]:
    if (
        command.executable == "python"
        and len(command.args) == 1
        and command.args[0].endswith(".py")
    ):
        return [
            "-c",
            (
                "import runpy; "
                f"ns=runpy.run_path({command.args[0]!r}); "
                "[value() for name, value in ns.items() "
                "if name.startswith('test_') and callable(value)]"
            ),
        ]

    return command.args
