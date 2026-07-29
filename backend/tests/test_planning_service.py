import asyncio
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.db.models.execution_plan import ExecutionPlan
from app.db.models.code_index import RepositoryFile
from app.db.models.task import RepoPilotTask
from app.db.session import (
    AsyncSessionLocal,
    engine,
)
from app.services.indexing.indexer import (
    index_repository,
)
from app.services.planning.service import (
    PlanStateError,
    PlannerService,
    apply_safe_planning_defaults,
)
from app.services.planning.validation import (
    PlanValidationError,
)
from app.services.tasks.service import TaskService
from app.services.tasks.state_machine import (
    PLAN_REVISION_REQUIRED,
    RETRIEVING,
)
from app.schemas.planning import (
    ImplementationStep,
    PlannedFile,
    SourceReference,
)
from tests.planning_fixtures import (
    FakePlannerRunner,
    insufficient_context_output,
    valid_planner_output,
)
from tests.retrieval_fixtures import (
    create_retrieval_fixture_repo,
)


ISSUE = {
    "number": 142,
    "title": "Search doesn't debounce correctly",
    "body": (
        "Search request fires for every keypress.\n"
        "Wait briefly before calling the API."
    ),
}

CONTEXT_PACK = {
    "query": ISSUE["title"],
    "estimated_tokens": 250,
    "files": [
        {
            "path": "src/components/SearchBox.tsx",
            "chunks": [
                {
                    "symbol": "SearchBox",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 8,
                    "content": "export function SearchBox() {}",
                    "matched_by": [
                        "semantic"
                    ],
                }
            ],
        }
    ],
}


def test_framework_specific_test_request_does_not_use_plain_file_default():
    output = insufficient_context_output()

    normalized = apply_safe_planning_defaults(
        output=output,
        issue={
            "number": 146,
            "title": "Add a pytest test file",
            "body": "Create a unit test for age.txt.",
        },
    )

    assert normalized is output
    assert normalized.needs_more_context is True
    assert normalized.files_to_modify == []


async def setup_workspace(
    tmp_path: Path,
    workspace_id: str,
) -> Path:
    repo = tmp_path / "repo"
    create_retrieval_fixture_repo(repo)

    async with AsyncSessionLocal() as db:
        await index_repository(
            workspace_id,
            repo,
            db,
        )
    await engine.dispose()

    return repo


async def delete_workspace(
    workspace_id: str,
) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(ExecutionPlan).where(
                ExecutionPlan.workspace_id
                == workspace_id
            )
        )
        await db.execute(
            delete(RepositoryFile).where(
                RepositoryFile.workspace_id
                == workspace_id
            )
        )
        await db.commit()


async def count_workspace_plans(
    workspace_id: str,
) -> int:
    async with AsyncSessionLocal() as db:
        return (
            await db.scalar(
                select(func.count())
                .select_from(ExecutionPlan)
                .where(
                    ExecutionPlan.workspace_id
                    == workspace_id
                )
            )
            or 0
        )


async def dispose_database_engine() -> None:
    await engine.dispose()


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


def test_create_plan_persists_pending_and_transitions_without_source_changes(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())

    async def run_test():
        repo = await setup_workspace(
            tmp_path,
            workspace_id,
        )
        before_status = git_status(repo)

        try:
            async with AsyncSessionLocal() as db:
                service = PlannerService(
                    planner_runner=FakePlannerRunner(
                        valid_planner_output()
                    )
                )
                plan = await service.create_plan(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    owner="acme",
                    repo="storefront",
                    issue=ISSUE,
                    context_pack=CONTEXT_PACK,
                    db=db,
                )

                assert plan.status == "pending_approval"
                assert plan.planner_model == "fake-planner-model"
                assert plan.input_tokens == 100

                approved = await service.approve_plan(
                    plan_id=plan.id,
                    db=db,
                )
                assert approved.status == "approved"

                with pytest.raises(
                    PlanStateError
                ):
                    await service.approve_plan(
                        plan_id=plan.id,
                        db=db,
                    )

            async with AsyncSessionLocal() as db:
                rejected_plan = await PlannerService(
                    planner_runner=FakePlannerRunner(
                        valid_planner_output()
                    )
                ).create_plan(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    owner="acme",
                    repo="storefront",
                    issue=ISSUE,
                    context_pack=CONTEXT_PACK,
                    db=db,
                )
                rejected = await PlannerService().reject_plan(
                    plan_id=rejected_plan.id,
                    reason="Needs a smaller scope",
                    db=db,
                )
                assert rejected.status == "rejected"
                assert rejected.rejection_reason == "Needs a smaller scope"

                with pytest.raises(
                    PlanStateError
                ):
                    await PlannerService().reject_plan(
                        plan_id=rejected_plan.id,
                        reason=None,
                        db=db,
                    )

            assert git_status(repo) == before_status
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_hallucinated_file_is_rejected_and_not_persisted(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())

    async def run_test():
        repo = await setup_workspace(
            tmp_path,
            workspace_id,
        )
        output = valid_planner_output()
        output.files_to_modify[0].path = "src/services/DebounceManager.ts"

        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    PlanValidationError
                ):
                    await PlannerService(
                        planner_runner=FakePlannerRunner(
                            output
                        )
                    ).create_plan(
                        workspace_id=workspace_id,
                        repository_path=repo,
                        owner="acme",
                        repo="storefront",
                        issue=ISSUE,
                        context_pack=CONTEXT_PACK,
                        db=db,
                    )

            assert await count_workspace_plans(
                workspace_id
            ) == 0
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_text_only_repository_can_plan_an_explicit_new_file(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "age.txt").write_text(
        "22\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "git",
            "init",
            "-q",
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "add",
            ".",
        ],
        cwd=repo,
        check=True,
    )

    output = valid_planner_output()
    output.files_to_inspect = [
        PlannedFile(
            path="age.txt",
            reason="Use the existing text fixture as repository context.",
            references=[
                SourceReference(
                    file_path="age.txt",
                    start_line=1,
                    end_line=1,
                )
            ],
        )
    ]
    output.files_to_modify = [
        PlannedFile(
            path="test.txt",
            change_type="create",
            reason="The issue explicitly requests a new test file.",
            references=[],
        )
    ]
    output.implementation_steps = [
        ImplementationStep(
            order=1,
            description="Create the requested test text file.",
            files=[
                "test.txt"
            ],
        )
    ]

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                index_result = await index_repository(
                    workspace_id,
                    repo,
                    db,
                )
                plan = await PlannerService(
                    planner_runner=FakePlannerRunner(
                        output
                    )
                ).create_plan(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    owner="acme",
                    repo="text-only",
                    issue={
                        "number": 1,
                        "title": "Add a test text file",
                        "body": "Create test.txt.",
                    },
                    context_pack={
                        "query": "Add a test text file",
                        "estimated_tokens": 10,
                        "files": [],
                    },
                    db=db,
                )

                assert index_result["files_indexed"] == 1
                assert plan.plan_json[
                    "files_to_modify"
                ][0]["change_type"] == "create"
                assert not (
                    repo / "test.txt"
                ).exists()
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_generic_test_file_request_gets_safe_minimal_create_plan(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    task_id: uuid.UUID | None = None

    async def run_test():
        nonlocal task_id
        repo = await setup_workspace(
            tmp_path,
            workspace_id,
        )

        try:
            async with AsyncSessionLocal() as db:
                task = await TaskService().create_task(
                    owner="acme",
                    repo="storefront",
                    issue_number=144,
                    db=db,
                    autonomy_mode="standard",
                )
                task_id = task.id
                task.workspace_id = workspace_id
                task.status = RETRIEVING
                task.current_step = 4
                await db.commit()

                plan = await PlannerService(
                    planner_runner=FakePlannerRunner(
                        insufficient_context_output()
                    )
                ).create_plan(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    owner="acme",
                    repo="storefront",
                    issue={
                        "number": 144,
                        "title": "Test Issue",
                        "body": (
                            "I am testing my app. "
                            "Fix: add new file test file."
                        ),
                    },
                    context_pack={
                        "query": "add new file test file",
                        "estimated_tokens": 10,
                        "files": [],
                    },
                    db=db,
                    task_id=task.id,
                )

                planned_files = plan.plan_json[
                    "files_to_modify"
                ]
                assert planned_files == [
                    {
                        "path": "test.txt",
                        "change_type": "create",
                        "reason": (
                            "The issue explicitly requests a new test file; "
                            "use a minimal plain-text artifact without adding "
                            "dependencies."
                        ),
                        "references": [],
                    }
                ]
                assert plan.plan_json[
                    "needs_more_context"
                ] is False
                assert plan.plan_json[
                    "missing_context"
                ] == []
                assert plan.plan_json[
                    "implementation_steps"
                ][0]["files"] == [
                    "test.txt"
                ]
                assert plan.status == "approved"
                planned_task = await db.get(
                    RepoPilotTask,
                    task.id,
                )
                assert planned_task is not None
                assert planned_task.status == "plan_approved"
        finally:
            if task_id is not None:
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        delete(RepoPilotTask).where(
                            RepoPilotTask.id
                            == task_id
                        )
                    )
                    await db.commit()
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_standard_task_stops_before_coding_when_plan_needs_context(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    task_id: uuid.UUID | None = None

    async def run_test():
        nonlocal task_id
        repo = await setup_workspace(
            tmp_path,
            workspace_id,
        )

        try:
            async with AsyncSessionLocal() as db:
                task = await TaskService().create_task(
                    owner="acme",
                    repo="storefront",
                    issue_number=145,
                    db=db,
                    autonomy_mode="standard",
                )
                task_id = task.id
                task.workspace_id = workspace_id
                task.status = RETRIEVING
                task.current_step = 4
                await db.commit()

                plan = await PlannerService(
                    planner_runner=FakePlannerRunner(
                        insufficient_context_output()
                    )
                ).create_plan(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    owner="acme",
                    repo="storefront",
                    issue={
                        "number": 145,
                        "title": "Search is broken",
                        "body": "",
                    },
                    context_pack={
                        "query": "Search is broken",
                        "estimated_tokens": 10,
                        "files": [],
                    },
                    db=db,
                    task_id=task.id,
                )
                stopped_task = await db.get(
                    RepoPilotTask,
                    task.id,
                )

                assert plan.status == "pending_approval"
                assert stopped_task is not None
                assert (
                    stopped_task.status
                    == PLAN_REVISION_REQUIRED
                )
                assert (
                    stopped_task.active_plan_id
                    == plan.id
                )
                assert (
                    stopped_task.last_error_type
                    == "PlannerNeedsMoreContext"
                )
                with pytest.raises(
                    PlanStateError
                ):
                    await PlannerService().approve_plan(
                        plan_id=plan.id,
                        db=db,
                    )
        finally:
            if task_id is not None:
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        delete(RepoPilotTask).where(
                            RepoPilotTask.id
                            == task_id
                        )
                    )
                    await db.commit()
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_invalid_line_reference_is_rejected(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())

    async def run_test():
        repo = await setup_workspace(
            tmp_path,
            workspace_id,
        )
        output = valid_planner_output()
        output.files_to_inspect[0].references[0].start_line = 500
        output.files_to_inspect[0].references[0].end_line = 550

        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    PlanValidationError
                ):
                    await PlannerService(
                        planner_runner=FakePlannerRunner(
                            output
                        )
                    ).create_plan(
                        workspace_id=workspace_id,
                        repository_path=repo,
                        owner="acme",
                        repo="storefront",
                        issue=ISSUE,
                        context_pack=CONTEXT_PACK,
                        db=db,
                    )
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_insufficient_context_plan_preserves_missing_context(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())

    async def run_test():
        repo = await setup_workspace(
            tmp_path,
            workspace_id,
        )

        try:
            async with AsyncSessionLocal() as db:
                plan = await PlannerService(
                    planner_runner=FakePlannerRunner(
                        insufficient_context_output()
                    )
                ).create_plan(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    owner="acme",
                    repo="storefront",
                    issue={
                        "number": 143,
                        "title": "Search is broken",
                        "body": "",
                    },
                    context_pack={
                        "query": "Search is broken",
                        "estimated_tokens": 10,
                        "files": [],
                    },
                    db=db,
                )

                assert plan.status == "pending_approval"
                assert plan.plan_json["needs_more_context"] is True
                assert plan.plan_json["missing_context"] == [
                    "Search entry point",
                    "Request-triggering code",
                ]
                with pytest.raises(
                    PlanStateError
                ):
                    await PlannerService().approve_plan(
                        plan_id=plan.id,
                        db=db,
                    )
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())
