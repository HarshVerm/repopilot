import subprocess
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from app.db.models.change_set import (
    ChangeSet,
    ChangeSetFile,
)
from app.db.models.debug_attempt import DebugAttempt
from app.db.models.execution_plan import ExecutionPlan
from app.db.models.execution_run import ExecutionRun
from app.db.session import AsyncSessionLocal
from app.services.changes.diff import (
    summarize_diff,
)
from app.services.changes.git import (
    get_base_commit_sha,
)
from app.services.sandbox.docker import (
    SandboxExecutionError,
    SandboxHandle,
)
from app.services.sandbox.filesystem import (
    cleanup_sandbox,
    create_sandbox_copy,
)
from app.services.sandbox.results import (
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_TIMEOUT,
    CommandResult,
    ExecutionCommand,
)
from tests.coding_fixtures import (
    create_coding_fixture_repo,
    fixed_searchbox_content,
    run_git,
    write_file,
)
from tests.planning_fixtures import (
    valid_planner_output,
)


ISSUE_NUMBER = 142


def create_node_execution_fixture_repo(
    repo: Path,
    *,
    scripts: dict[str, str] | None = None,
) -> None:
    create_coding_fixture_repo(repo)
    write_file(
        repo,
        "package.json",
        package_json(
            scripts
            or {
                "test": "vitest run",
                "typecheck": "tsc --noEmit",
                "lint": "eslint .",
                "build": "tsc",
            }
        ),
    )
    write_file(
        repo,
        "package-lock.json",
        "{}\n",
    )
    run_git(
        repo,
        [
            "add",
            "package.json",
            "package-lock.json",
        ],
    )
    run_git(
        repo,
        [
            "-c",
            "user.name=RepoPilot Test",
            "-c",
            "user.email=repopilot@example.com",
            "commit",
            "-m",
            "add node project metadata",
            "-q",
        ],
    )
    apply_searchbox_patch(repo)


def package_json(
    scripts: dict[str, str],
) -> str:
    items = ",\n".join(
        f'    "{name}": "{value}"'
        for name, value in scripts.items()
    )

    return (
        "{\n"
        '  "scripts": {\n'
        f"{items}\n"
        "  }\n"
        "}\n"
    )


def apply_searchbox_patch(
    repo: Path,
) -> None:
    (
        repo / "src/components/SearchBox.tsx"
    ).write_text(
        fixed_searchbox_content(),
        encoding="utf-8",
    )


async def seed_execution_plan(
    *,
    workspace_id: str,
) -> ExecutionPlan:
    output = valid_planner_output()

    async with AsyncSessionLocal() as db:
        plan = ExecutionPlan(
            workspace_id=workspace_id,
            repository_owner="acme",
            repository_name="storefront",
            issue_number=ISSUE_NUMBER,
            status="approved",
            summary=output.summary,
            problem_analysis=(
                output.problem_analysis
            ),
            likely_root_cause=(
                output.likely_root_cause
            ),
            confidence=output.confidence,
            plan_json=output.model_dump(
                mode="json"
            ),
        )
        db.add(plan)
        await db.commit()
        await db.refresh(plan)

        return plan


async def seed_generated_change_set(
    *,
    workspace_id: str,
    repo: Path,
    status: str = "generated",
) -> ChangeSet:
    plan = await seed_execution_plan(
        workspace_id=workspace_id
    )
    base_commit_sha = get_base_commit_sha(
        repo
    )
    diff_summary = summarize_diff(
        repo
    )

    async with AsyncSessionLocal() as db:
        change_set = ChangeSet(
            workspace_id=workspace_id,
            plan_id=plan.id,
            plan_version=1,
            approved_plan_json=plan.plan_json,
            status=status,
            base_commit_sha=base_commit_sha,
            summary="Generated debounce patch.",
            diff=diff_summary.diff,
            files_changed=len(
                diff_summary.files
            ),
            lines_added=(
                diff_summary.lines_added
            ),
            lines_deleted=(
                diff_summary.lines_deleted
            ),
            before_tree_hash="before",
            after_tree_hash="after",
        )
        db.add(change_set)

        for file in diff_summary.files:
            change_set.files.append(
                ChangeSetFile(
                    path=file.path,
                    before_sha256=file.before_sha256,
                    after_sha256=file.after_sha256,
                    lines_added=file.lines_added,
                    lines_deleted=file.lines_deleted,
                )
            )

        await db.commit()
        await db.refresh(
            change_set,
            attribute_names=["files"],
        )

        return change_set


async def cleanup_execution_workspace(
    workspace_id: str,
) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(DebugAttempt).where(
                DebugAttempt.workspace_id
                == workspace_id
            )
        )
        await db.execute(
            delete(ExecutionRun).where(
                ExecutionRun.workspace_id
                == workspace_id
            )
        )

        result = await db.execute(
            select(
                ChangeSet.id,
                ChangeSet.parent_change_set_id,
            ).where(
                ChangeSet.workspace_id
                == workspace_id
            )
        )
        remaining = {
            row.id: row.parent_change_set_id
            for row in result
        }

        while remaining:
            leaves = [
                change_set_id
                for change_set_id in remaining
                if change_set_id
                not in set(remaining.values())
            ]

            if not leaves:
                leaves = list(remaining)

            for change_set_id in leaves:
                await db.execute(
                    delete(ChangeSet).where(
                        ChangeSet.id
                        == change_set_id
                    )
                )
                remaining.pop(
                    change_set_id,
                    None,
                )

        await db.execute(
            delete(ExecutionPlan).where(
                ExecutionPlan.workspace_id
                == workspace_id
            )
        )
        await db.commit()


def git_status(
    repo: Path,
) -> str:
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
        ],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )

    return result.stdout


class FakeSandbox:
    runtime_name = "fake-docker"

    def __init__(
        self,
        *,
        sandbox_root: Path,
        statuses: dict[str, str] | None = None,
        mutate_sandbox: bool = False,
        raise_on_execute: bool = False,
    ) -> None:
        self.sandbox_root = sandbox_root
        self.statuses = statuses or {}
        self.mutate_sandbox = mutate_sandbox
        self.raise_on_execute = raise_on_execute
        self.executed: list[ExecutionCommand] = []
        self.cleanup_called = False
        self.last_handle: SandboxHandle | None = None

    def prepare(
        self,
        *,
        execution_run_id: uuid.UUID,
        source_repository: Path,
    ) -> SandboxHandle:
        repository_path = create_sandbox_copy(
            execution_run_id=execution_run_id,
            source_repository=source_repository,
            sandbox_root=self.sandbox_root,
        )
        self.last_handle = SandboxHandle(
            execution_run_id=execution_run_id,
            run_directory=repository_path.parent,
            repository_path=repository_path,
        )
        return self.last_handle

    def execute(
        self,
        *,
        handle: SandboxHandle,
        command: ExecutionCommand,
    ) -> CommandResult:
        self.executed.append(command)

        if self.raise_on_execute:
            raise SandboxExecutionError(
                "Docker unavailable"
            )

        if self.mutate_sandbox:
            (
                handle.repository_path
                / "src/components/SearchBox.tsx"
            ).write_text(
                "mutated inside sandbox\n",
                encoding="utf-8",
            )

        status = self.statuses.get(
            command.name,
            STATUS_PASS,
        )
        exit_code = 0

        if status == STATUS_FAIL:
            exit_code = 1
        elif status in {
            STATUS_TIMEOUT,
            STATUS_ERROR,
        }:
            exit_code = None

        return CommandResult(
            name=command.name,
            command_type=command.command_type,
            status=status,
            exit_code=exit_code,
            duration_ms=12.0,
            stdout=(
                "ok\n"
                if status == STATUS_PASS
                else "failure\n"
            ),
            stderr="",
        )

    def cleanup(
        self,
        handle: SandboxHandle | None,
    ) -> list[str]:
        self.cleanup_called = True

        if handle:
            cleanup_sandbox(
                handle.run_directory,
                sandbox_root=self.sandbox_root,
            )

        return []
