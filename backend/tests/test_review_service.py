import asyncio
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.models.change_set import (
    ChangeSet,
    ChangeSetFile,
)
from app.db.models.execution_run import (
    ExecutionRun,
)
from app.db.models.debug_attempt import (
    DebugAttempt,
)
from app.db.models.final_review import (
    FinalReview,
)
from app.db.session import (
    AsyncSessionLocal,
    engine,
)
from app.services.changes.diff import (
    summarize_diff,
)
from app.services.changes.git import (
    get_base_commit_sha,
)
from app.services.changes.hashing import (
    diff_hash,
)
from app.services.reviews.service import (
    APPROVED,
    PENDING_REVIEW,
    REJECTED,
    ExecutionMismatchError,
    ReviewAlreadyExistsError,
    ReviewNotEligibleError,
    ReviewService,
    ReviewStateError,
    WorkspaceDriftError,
)
from app.services.sandbox.results import (
    BUILD,
    EXECUTION_FAILED,
    EXECUTION_PASSED,
    EXECUTION_TIMEOUT,
    LINT,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
    TEST,
    TYPECHECK,
    check_statuses,
)
from tests.coding_fixtures import (
    fixed_searchbox_content,
    run_git,
)
from tests.debugging_fixtures import (
    alternate_searchbox_content,
    command_result,
    execution_command,
    seed_execution_run,
)
from tests.execution_fixtures import (
    cleanup_execution_workspace,
    create_node_execution_fixture_repo,
    seed_generated_change_set,
)


def test_create_review_freezes_successful_change_set():
    workspace = prepare_review_workspace()
    head_before = get_base_commit_sha(
        workspace.repo
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                review = await ReviewService().create_review(
                    change_set_id=workspace.change_set.id,
                    repository_path=workspace.repo,
                    db=db,
                )

                assert review.status == PENDING_REVIEW
                assert review.reviewed_at is None
                assert review.base_commit_sha == workspace.change_set.base_commit_sha
                assert review.diff_hash == workspace.change_set.diff_hash
                assert review.change_set_id == workspace.change_set.id
                assert review.execution_run_id == workspace.execution_run.id
                assert review.files_changed == 1
                assert review.files_json[0]["path"] == "src/components/SearchBox.tsx"
                assert review.files_json[0]["change_type"] == "modified"
                assert review.verification_json["checks"]["tests"] == STATUS_PASS
                assert review.verification_json["checks"]["lint"] == STATUS_SKIPPED
                assert "lint SKIPPED" in review.risk_summary
                assert "no dependency changes" in review.risk_summary
                assert "no debugger retries" in review.risk_summary
                assert review.issue_json["issue_number"] == 142
                assert review.plan_snapshot_json["status"] == "approved"
                assert str(workspace.repo) not in review.diff

            assert get_base_commit_sha(
                workspace.repo
            ) == head_before
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_approve_review_revalidates_and_is_one_time():
    workspace = prepare_review_workspace()

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = ReviewService()
                review = await service.create_review(
                    change_set_id=workspace.change_set.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                frozen = (
                    review.change_set_id,
                    review.execution_run_id,
                    review.base_commit_sha,
                    review.diff_hash,
                    review.diff,
                )
                approved = await service.approve_review(
                    review_id=review.id,
                    repository_path=workspace.repo,
                    db=db,
                )

                assert approved.status == APPROVED
                assert approved.decision == APPROVED
                assert approved.reviewed_at is not None
                assert (
                    approved.change_set_id,
                    approved.execution_run_id,
                    approved.base_commit_sha,
                    approved.diff_hash,
                    approved.diff,
                ) == frozen

                with pytest.raises(
                    ReviewStateError
                ):
                    await service.approve_review(
                        review_id=review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )

                with pytest.raises(
                    ReviewStateError
                ):
                    await service.reject_review(
                        review_id=review.id,
                        rejection_reason="Nope",
                        db=db,
                    )
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_reject_review_persists_reason_and_stops():
    workspace = prepare_review_workspace()
    before = git_status(
        workspace.repo
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = ReviewService()
                review = await service.create_review(
                    change_set_id=workspace.change_set.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                rejected = await service.reject_review(
                    review_id=review.id,
                    rejection_reason=(
                        "Keep the debounce delay configurable."
                    ),
                    db=db,
                )

                assert rejected.status == REJECTED
                assert rejected.decision == REJECTED
                assert rejected.rejection_reason == (
                    "Keep the debounce delay configurable."
                )
                assert rejected.reviewed_at is not None

                with pytest.raises(
                    ReviewStateError
                ):
                    await service.reject_review(
                        review_id=review.id,
                        rejection_reason="Again",
                        db=db,
                    )

                with pytest.raises(
                    ReviewStateError
                ):
                    await service.approve_review(
                        review_id=review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )

            assert git_status(
                workspace.repo
            ) == before
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_workspace_tampering_blocks_approval():
    workspace = prepare_review_workspace()

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = ReviewService()
                review = await service.create_review(
                    change_set_id=workspace.change_set.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                review_hash = review.diff_hash

            (
                workspace.repo
                / "src/components/SearchBox.tsx"
            ).write_text(
                fixed_searchbox_content()
                + "\n// tampered\n",
                encoding="utf-8",
            )
            modified_hash = diff_hash(
                summarize_diff(
                    workspace.repo
                ).diff
            )

            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    WorkspaceDriftError
                ):
                    await ReviewService().approve_review(
                        review_id=review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                saved = await db.get(
                    FinalReview,
                    review.id,
                )

                assert saved.status == PENDING_REVIEW
                assert modified_hash != review_hash
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_base_commit_drift_blocks_approval():
    workspace = prepare_review_workspace()

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                review = await ReviewService().create_review(
                    change_set_id=workspace.change_set.id,
                    repository_path=workspace.repo,
                    db=db,
                )

            run_git(
                workspace.repo,
                [
                    "add",
                    "src/components/SearchBox.tsx",
                ],
            )
            run_git(
                workspace.repo,
                [
                    "-c",
                    "user.name=RepoPilot Test",
                    "-c",
                    "user.email=repopilot@example.com",
                    "commit",
                    "-m",
                    "advance base",
                    "-q",
                ],
            )

            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    WorkspaceDriftError
                ):
                    await ReviewService().approve_review(
                        review_id=review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                saved = await db.get(
                    FinalReview,
                    review.id,
                )

                assert saved.status == PENDING_REVIEW
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_wrong_execution_run_cannot_be_approved():
    workspace = prepare_review_workspace()

    async def run_test():
        try:
            child = await seed_child_change_set(
                workspace=workspace,
                content=alternate_searchbox_content(),
            )

            async with AsyncSessionLocal() as db:
                bad_review = FinalReview(
                    workspace_id=workspace.workspace_id,
                    plan_id=child.plan_id,
                    change_set_id=child.id,
                    execution_run_id=(
                        workspace.execution_run.id
                    ),
                    status=PENDING_REVIEW,
                    base_commit_sha=(
                        child.base_commit_sha
                    ),
                    diff_hash=child.diff_hash,
                    files_changed=child.files_changed,
                    lines_added=child.lines_added,
                    lines_deleted=(
                        child.lines_deleted
                    ),
                    summary=child.summary,
                    risk_summary="manual bad review",
                    files_json=[],
                    verification_json={},
                    debug_history_json={
                        "debug_attempts": 0,
                        "history": [],
                    },
                    issue_json={},
                    plan_snapshot_json={},
                    diff=child.diff or "",
                )
                db.add(
                    bad_review
                )
                await db.commit()
                await db.refresh(
                    bad_review
                )

                with pytest.raises(
                    ExecutionMismatchError
                ):
                    await ReviewService().approve_review(
                        review_id=bad_review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


@pytest.mark.parametrize(
    ("run_status", "result_status"),
    [
        (
            EXECUTION_FAILED,
            STATUS_FAIL,
        ),
        (
            EXECUTION_TIMEOUT,
            STATUS_TIMEOUT,
        ),
    ],
)
def test_failed_and_timeout_runs_cannot_create_review(
    run_status,
    result_status,
):
    workspace = prepare_review_workspace(
        execution_status=run_status,
        result_status=result_status,
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    ReviewNotEligibleError
                ):
                    await ReviewService().create_review(
                        change_set_id=workspace.change_set.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_duplicate_review_returns_existing_active_review():
    workspace = prepare_review_workspace()

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = ReviewService()
                first = await service.create_review(
                    change_set_id=workspace.change_set.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                second = await service.create_review(
                    change_set_id=workspace.change_set.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                count = await db.scalar(
                    select(
                        func.count()
                    )
                    .select_from(FinalReview)
                    .where(
                        FinalReview.change_set_id
                        == workspace.change_set.id
                    )
                )

                assert second.id == first.id
                assert count == 1
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_rejected_duplicate_requires_new_change_set():
    workspace = prepare_review_workspace()

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = ReviewService()
                review = await service.create_review(
                    change_set_id=workspace.change_set.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                await service.reject_review(
                    review_id=review.id,
                    rejection_reason="Needs revision.",
                    db=db,
                )

                with pytest.raises(
                    ReviewAlreadyExistsError
                ):
                    await service.create_review(
                        change_set_id=workspace.change_set.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_only_final_debug_change_set_can_be_reviewed():
    workspace = prepare_review_workspace()

    async def run_test():
        try:
            child = await seed_child_change_set(
                workspace=workspace,
                content=alternate_searchbox_content(),
            )

            async with AsyncSessionLocal() as db:
                child_run = await seed_passed_execution_run(
                    db=db,
                    workspace_id=workspace.workspace_id,
                    change_set_id=child.id,
                )
                await seed_debug_attempt(
                    db=db,
                    workspace=workspace,
                    child=child,
                    retry_run=child_run,
                )
                service = ReviewService()

                with pytest.raises(
                    ReviewNotEligibleError
                ):
                    await service.create_review(
                        change_set_id=workspace.change_set.id,
                        repository_path=workspace.repo,
                        db=db,
                    )

                review = await service.create_review(
                    change_set_id=child.id,
                    repository_path=workspace.repo,
                    db=db,
                )

                assert review.change_set_id == child.id
                assert (
                    review.debug_history_json[
                        "debug_attempts"
                    ]
                    == 1
                )
                assert "1 debugger attempt" in review.risk_summary
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_workspace_isolation_rejects_wrong_workspace_run():
    workspace = prepare_review_workspace(
        execution_workspace_id=str(
            uuid.uuid4()
        )
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    ReviewNotEligibleError
                ):
                    await ReviewService().create_review(
                        change_set_id=workspace.change_set.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
        finally:
            await cleanup_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


class ReviewWorkspace:
    def __init__(
        self,
        *,
        workspace_id: str,
        workspace_path: Path,
        repo: Path,
        change_set: ChangeSet,
        execution_run: ExecutionRun,
    ) -> None:
        self.workspace_id = workspace_id
        self.workspace_path = workspace_path
        self.repo = repo
        self.change_set = change_set
        self.execution_run = execution_run


def prepare_review_workspace(
    *,
    execution_status: str = EXECUTION_PASSED,
    result_status: str = STATUS_PASS,
    execution_workspace_id: str | None = None,
) -> ReviewWorkspace:
    workspace_id = str(
        uuid.uuid4()
    )
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    create_node_execution_fixture_repo(
        repo
    )
    async def seed_records():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        async with AsyncSessionLocal() as db:
            execution_run = await seed_passed_execution_run(
                db=db,
                workspace_id=(
                    execution_workspace_id
                    or workspace_id
                ),
                change_set_id=change_set.id,
                status=execution_status,
                result_status=result_status,
            )

        await engine.dispose()

        return (
            change_set,
            execution_run,
        )

    (
        change_set,
        execution_run,
    ) = asyncio.run(
        seed_records()
    )

    return ReviewWorkspace(
        workspace_id=workspace_id,
        workspace_path=workspace_path,
        repo=repo,
        change_set=change_set,
        execution_run=execution_run,
    )


async def seed_passed_execution_run(
    *,
    db,
    workspace_id: str,
    change_set_id,
    status: str = EXECUTION_PASSED,
    result_status: str = STATUS_PASS,
):
    if status == EXECUTION_PASSED:
        commands = [
            execution_command(TEST),
            execution_command(TYPECHECK),
            execution_command(LINT),
            execution_command(BUILD),
        ]
        results = [
            command_result(
                command=commands[0],
                result_status=result_status,
                stdout="PASS SearchBox\n",
                stderr="",
            ),
            command_result(
                command=commands[1],
                result_status=STATUS_PASS,
                stdout="PASS typecheck\n",
                stderr="",
            ),
            command_result(
                command=commands[2],
                result_status=STATUS_SKIPPED,
                stdout="",
                stderr="lint skipped\n",
            ),
            command_result(
                command=commands[3],
                result_status=STATUS_PASS,
                stdout="PASS build\n",
                stderr="",
            ),
        ]
        checks = check_statuses(
            results
        )
        now = datetime.now(
            UTC
        )
        run = ExecutionRun(
            change_set_id=change_set_id,
            workspace_id=workspace_id,
            status=status,
            started_at=now,
            completed_at=now,
            duration_ms=25.0,
            commands_json=[
                command.to_json()
                for command in commands
            ],
            results_json=[
                result.to_json()
                for result in results
            ],
            tests_status=checks["tests"],
            lint_status=checks["lint"],
            typecheck_status=(
                checks["typecheck"]
            ),
            build_status=checks["build"],
            timed_out=False,
            sandbox_runtime="fake-docker",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        return run

    return await seed_execution_run(
        db=db,
        workspace_id=workspace_id,
        change_set_id=change_set_id,
        status=status,
        result_status=result_status,
    )


async def seed_child_change_set(
    *,
    workspace: ReviewWorkspace,
    content: str,
) -> ChangeSet:
    (
        workspace.repo
        / "src/components/SearchBox.tsx"
    ).write_text(
        content,
        encoding="utf-8",
    )
    diff_summary = summarize_diff(
        workspace.repo
    )

    async with AsyncSessionLocal() as db:
        child = ChangeSet(
            workspace_id=workspace.workspace_id,
            plan_id=workspace.change_set.plan_id,
            parent_change_set_id=(
                workspace.change_set.id
            ),
            plan_version=(
                workspace.change_set.plan_version
            ),
            approved_plan_json=(
                workspace.change_set.approved_plan_json
            ),
            status="generated",
            base_commit_sha=(
                workspace.change_set.base_commit_sha
            ),
            summary="Debug repair patch.",
            diff=diff_summary.diff,
            diff_hash=diff_hash(
                diff_summary.diff
            ),
            files_changed=len(
                diff_summary.files
            ),
            lines_added=(
                diff_summary.lines_added
            ),
            lines_deleted=(
                diff_summary.lines_deleted
            ),
            before_tree_hash=(
                workspace.change_set.before_tree_hash
            ),
            after_tree_hash=diff_hash(
                diff_summary.diff
            ),
        )
        db.add(
            child
        )

        for file in diff_summary.files:
            child.files.append(
                ChangeSetFile(
                    path=file.path,
                    before_sha256=(
                        file.before_sha256
                    ),
                    after_sha256=(
                        file.after_sha256
                    ),
                    lines_added=(
                        file.lines_added
                    ),
                    lines_deleted=(
                        file.lines_deleted
                    ),
                )
            )

        await db.commit()
        await db.refresh(
            child,
            attribute_names=["files"],
        )

        return child


async def seed_debug_attempt(
    *,
    db,
    workspace: ReviewWorkspace,
    child: ChangeSet,
    retry_run: ExecutionRun,
) -> DebugAttempt:
    attempt = DebugAttempt(
        workspace_id=workspace.workspace_id,
        plan_id=workspace.change_set.plan_id,
        parent_change_set_id=(
            workspace.change_set.id
        ),
        new_change_set_id=child.id,
        failed_execution_run_id=(
            workspace.execution_run.id
        ),
        retry_execution_run_id=retry_run.id,
        attempt_number=1,
        status="passed",
        failure_category="test_failure",
        diagnosis="Use the debounced query in the effect dependency.",
        likely_root_cause="Effect depended on immediate query.",
        confidence=0.9,
        diff_hash=child.diff_hash,
        failure_fingerprint="fingerprint",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    return attempt


async def cleanup_workspace(
    workspace: ReviewWorkspace,
) -> None:
    await cleanup_execution_workspace(
        workspace.workspace_id
    )
    await engine.dispose()
    shutil.rmtree(
        workspace.workspace_path,
        ignore_errors=True,
    )


def git_status(
    repo: Path,
) -> str:
    return run_git_capture(
        repo,
        [
            "status",
            "--porcelain",
        ],
    )


def run_git_capture(
    repo: Path,
    args: list[str],
) -> str:
    import subprocess

    result = subprocess.run(
        [
            "git",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )

    return result.stdout
