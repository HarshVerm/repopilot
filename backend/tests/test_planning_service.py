import asyncio
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.db.models.execution_plan import ExecutionPlan
from app.db.models.code_index import RepositoryFile
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
)
from app.services.planning.validation import (
    PlanValidationError,
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
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())
