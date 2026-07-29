import asyncio

import pytest
from sqlalchemy import delete, func, select

from app.db.models.change_set import ChangeSet
from app.db.models.execution_plan import ExecutionPlan
from app.db.models.execution_run import ExecutionRun
from app.db.models.final_review import (
    FinalReview,
)
from app.db.models.publication import (
    Publication,
)
from app.db.models.task import RepoPilotTask
from app.db.session import AsyncSessionLocal
from app.services.publishing.authentication import (
    GitHubCredentials,
)
from app.services.publishing.git import (
    GitPushError,
    SafeGitPublisher,
)
from app.services.publishing.github import (
    PullRequestMetadata,
)
from app.services.publishing.integrity import (
    CommitDiffMismatchError,
    CommitParentMismatchError,
    PublicationIntegrityError,
    RepositoryMismatchError,
    ReviewNotApprovedError,
    StagedDiffMismatchError,
    StagedFileMismatchError,
)
from app.services.publishing.naming import (
    BranchNameError,
    generate_branch_name,
)
from app.services.publishing.service import (
    FAILED,
    PARTIALLY_PUBLISHED,
    PUBLISHED,
    PublicationService,
    build_commit_subject,
    build_pr_body,
)
from app.services.reviews.service import (
    PENDING_REVIEW,
    REJECTED,
    SUPERSEDED,
    WorkspaceDriftError,
)
from app.services.tasks.state_machine import (
    COMPLETED,
    FAILED as TASK_FAILED,
    REVIEW_APPROVED,
)
from tests.coding_fixtures import (
    run_git,
)
from tests.execution_fixtures import (
    ISSUE_NUMBER,
)
from tests.publishing_fixtures import (
    FakeGitHubPublisher,
    NEW_FILE_CONTENT,
    StaticAuthenticator,
    bare_remote_branch_sha,
    bare_remote_branches,
    cleanup_publishing_workspace,
    prepare_publishing_workspace,
    run_git_capture,
)


def test_publish_success_includes_approved_new_file():
    workspace = prepare_publishing_workspace(
        new_file=True
    )
    github = FakeGitHubPublisher()
    service = publication_service(
        github=github
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                publication = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )

                assert publication.status == PUBLISHED
                assert publication.working_tree_diff_hash == workspace.review.diff_hash
                assert publication.staged_diff_hash == workspace.review.diff_hash
                assert publication.commit_diff_hash == workspace.review.diff_hash

            assert run_git_capture(
                workspace.repo,
                [
                    "show",
                    f"{publication.commit_sha}:test.txt",
                ],
            ) == NEW_FILE_CONTENT
            assert run_git_capture(
                workspace.repo,
                [
                    "status",
                    "--porcelain",
                ],
            ) == ""
            assert bare_remote_branch_sha(
                workspace.bare_remote,
                publication.branch_name,
            ) == publication.commit_sha
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_failed_publication_can_retry_same_approved_task():
    workspace = prepare_publishing_workspace(
        new_file=True
    )
    github = FakeGitHubPublisher()
    factory = FailingWorkingDiffOnceFactory()
    service = publication_service(
        github=github,
        git_factory=factory,
    )
    task_id = None

    async def run_test():
        nonlocal task_id
        try:
            async with AsyncSessionLocal() as db:
                plan = await db.get(
                    ExecutionPlan,
                    workspace.review.plan_id,
                )
                change_set = await db.get(
                    ChangeSet,
                    workspace.change_set.id,
                )
                execution_run = await db.get(
                    ExecutionRun,
                    workspace.execution_run.id,
                )
                review = await db.get(
                    FinalReview,
                    workspace.review.id,
                )
                assert plan is not None
                assert change_set is not None
                assert execution_run is not None
                assert review is not None

                task = RepoPilotTask(
                    repository_owner="acme",
                    repository_name="storefront",
                    issue_number=142,
                    workspace_id=workspace.workspace_id,
                    status=REVIEW_APPROVED,
                    current_step=9,
                    autonomy_mode="standard",
                )
                db.add(task)
                await db.flush()
                task_id = task.id
                plan.task_id = task.id
                change_set.task_id = task.id
                execution_run.task_id = task.id
                review.task_id = task.id
                task.active_plan_id = plan.id
                task.active_change_set_id = change_set.id
                task.active_execution_run_id = execution_run.id
                task.active_review_id = review.id
                await db.commit()

                with pytest.raises(
                    PublicationIntegrityError
                ):
                    await service.publish_review(
                        review_id=review.id,
                        repository_path=workspace.repo,
                        db=db,
                        task_id=task.id,
                    )

                failed_task = await db.get(
                    RepoPilotTask,
                    task.id,
                )
                failed_publication = await publication_for_review(
                    db,
                    review.id,
                )
                assert failed_task is not None
                assert failed_task.status == TASK_FAILED
                assert failed_task.retryable is True
                assert failed_publication.status == FAILED

                retried = await service.publish_review(
                    review_id=review.id,
                    repository_path=workspace.repo,
                    db=db,
                    task_id=task.id,
                )
                completed_task = await db.get(
                    RepoPilotTask,
                    task.id,
                )
                assert completed_task is not None
                assert completed_task.status == COMPLETED
                assert completed_task.last_error is None
                assert completed_task.last_error_type is None
                assert completed_task.failure_category is None
                assert completed_task.retryable is None
                assert retried.id == failed_publication.id
                assert retried.status == PUBLISHED
                assert retried.retry_count == 1
                assert len(github.created_requests) == 1
        finally:
            await cleanup_publishing_workspace(
                workspace
            )
            if task_id is not None:
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        delete(RepoPilotTask).where(
                            RepoPilotTask.id
                            == task_id
                        )
                    )
                    await db.commit()

    asyncio.run(
        run_test()
    )


def test_publish_success_creates_exact_branch_commit_push_and_pr():
    workspace = prepare_publishing_workspace()
    github = FakeGitHubPublisher()
    service = publication_service(
        github=github
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                publication = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                count = await publication_count(
                    db,
                    workspace.review.id,
                )

                assert publication.status == PUBLISHED
                assert count == 1
                assert publication.branch_name.startswith(
                    "repopilot/142-"
                )
                assert publication.branch_name != "main"
                assert publication.base_branch == "main"
                assert publication.working_tree_diff_hash == workspace.review.diff_hash
                assert publication.staged_diff_hash == workspace.review.diff_hash
                assert publication.commit_diff_hash == workspace.review.diff_hash
                assert publication.remote_head_sha == publication.commit_sha
                assert publication.pull_request_number == 1
                assert publication.pull_request_url

            assert run_git_capture(
                workspace.repo,
                [
                    "status",
                    "--porcelain",
                ],
            ) == ""
            assert bare_remote_branch_sha(
                workspace.bare_remote,
                publication.branch_name,
            ) == publication.commit_sha
            assert bare_remote_branch_sha(
                workspace.bare_remote,
                "main",
            ) == workspace.review.base_commit_sha
            assert github.created_requests[0]["base"] == "main"
            assert github.created_requests[0]["head"] == publication.branch_name
            assert "Lint: Skipped" in github.created_requests[0]["body"]
            assert "Typecheck: Skipped" in github.created_requests[0]["body"]
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_publish_is_idempotent_for_same_review():
    workspace = prepare_publishing_workspace()
    github = FakeGitHubPublisher()
    service = publication_service(
        github=github
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                first = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                second = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                count = await publication_count(
                    db,
                    workspace.review.id,
                )

                assert second.id == first.id
                assert second.commit_sha == first.commit_sha
                assert second.pull_request_number == first.pull_request_number
                assert count == 1
                assert len(github.created_requests) == 1
                assert sorted(
                    bare_remote_branches(
                        workspace.bare_remote
                    )
                ) == sorted(
                    [
                        "main",
                        first.branch_name,
                    ]
                )
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


@pytest.mark.parametrize(
    "status",
    [
        PENDING_REVIEW,
        REJECTED,
        SUPERSEDED,
    ],
)
def test_unapproved_reviews_cannot_publish(
    status,
):
    workspace = prepare_publishing_workspace()
    service = publication_service()

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                review = await db.get(
                    FinalReview,
                    workspace.review.id,
                )
                review.status = status
                await db.commit()

            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    ReviewNotApprovedError
                ):
                    await service.publish_review(
                        review_id=workspace.review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                assert await publication_count(
                    db,
                    workspace.review.id,
                ) == 0
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_tampering_before_publish_is_blocked_before_branch_creation():
    workspace = prepare_publishing_workspace()
    service = publication_service()

    (
        workspace.repo
        / "src/components/SearchBox.tsx"
    ).write_text(
        "tampered\n",
        encoding="utf-8",
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    WorkspaceDriftError
                ):
                    await service.publish_review(
                        review_id=workspace.review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                assert await publication_count(
                    db,
                    workspace.review.id,
                ) == 0
                invalidated_review = await db.get(
                    FinalReview,
                    workspace.review.id,
                )
                assert invalidated_review is not None
                assert (
                    invalidated_review.status
                    == PENDING_REVIEW
                )
                assert invalidated_review.decision is None

            assert bare_remote_branches(
                workspace.bare_remote
            ) == [
                "main"
            ]
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_staging_attack_is_blocked_before_commit():
    workspace = prepare_publishing_workspace()
    service = publication_service()
    (
        workspace.repo / "README.md"
    ).write_text(
        "unreviewed\n",
        encoding="utf-8",
    )
    run_git(
        workspace.repo,
        [
            "add",
            "README.md",
        ],
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    StagedFileMismatchError
                ):
                    await service.publish_review(
                        review_id=workspace.review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                publication = await publication_for_review(
                    db,
                    workspace.review.id,
                )
                assert publication.status == FAILED
                assert publication.commit_sha is None

            assert run_git_capture(
                workspace.repo,
                [
                    "rev-parse",
                    "HEAD",
                ],
            ).strip() == workspace.review.base_commit_sha
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_staged_diff_mismatch_is_blocked_before_commit():
    workspace = prepare_publishing_workspace()
    service = publication_service(
        git_cls=TamperingStageGitPublisher
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    StagedDiffMismatchError
                ):
                    await service.publish_review(
                        review_id=workspace.review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                publication = await publication_for_review(
                    db,
                    workspace.review.id,
                )
                assert publication.status == FAILED
                assert publication.commit_sha is None
                assert publication.staged_diff_hash != workspace.review.diff_hash
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_commit_diff_mismatch_is_blocked_before_push():
    workspace = prepare_publishing_workspace()
    service = publication_service(
        git_cls=CommitDiffMismatchGitPublisher
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    CommitDiffMismatchError
                ):
                    await service.publish_review(
                        review_id=workspace.review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                publication = await publication_for_review(
                    db,
                    workspace.review.id,
                )
                assert publication.status == FAILED
                assert publication.commit_sha
                assert publication.commit_diff_hash != workspace.review.diff_hash

            assert bare_remote_branches(
                workspace.bare_remote
            ) == [
                "main"
            ]
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_wrong_parent_is_blocked_before_push():
    workspace = prepare_publishing_workspace()
    service = publication_service(
        git_cls=WrongParentGitPublisher
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    CommitParentMismatchError
                ):
                    await service.publish_review(
                        review_id=workspace.review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                publication = await publication_for_review(
                    db,
                    workspace.review.id,
                )
                assert publication.status == FAILED
                assert publication.commit_sha

            assert bare_remote_branches(
                workspace.bare_remote
            ) == [
                "main"
            ]
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_wrong_repository_snapshot_is_blocked():
    workspace = prepare_publishing_workspace()
    service = publication_service()

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                review = await db.get(
                    FinalReview,
                    workspace.review.id,
                )
                review.issue_json = {
                    **review.issue_json,
                    "repository_owner": "evil",
                }
                await db.commit()

            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    RepositoryMismatchError
                ):
                    await service.publish_review(
                        review_id=workspace.review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_default_branch_name_is_blocked():
    workspace = prepare_publishing_workspace()
    service = DefaultBranchPublicationService(
        github_publisher=FakeGitHubPublisher(),
        authenticator=StaticAuthenticator(),
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    BranchNameError
                ):
                    await service.publish_review(
                        review_id=workspace.review.id,
                        repository_path=workspace.repo,
                        db=db,
                    )
                publication = await publication_for_review(
                    db,
                    workspace.review.id,
                )
                assert publication.status == FAILED
                assert publication.commit_sha is None
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_branch_collision_uses_safe_alternative():
    workspace = prepare_publishing_workspace()
    base_branch = generate_branch_name(
        issue_number=ISSUE_NUMBER,
        summary=workspace.review.summary or "change",
        diff_hash=workspace.review.diff_hash,
    )
    run_git(
        workspace.repo,
        [
            "push",
            "origin",
            f"HEAD:refs/heads/{base_branch}",
        ],
    )
    service = publication_service()

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                publication = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )

                assert publication.status == PUBLISHED
                assert publication.branch_name != base_branch
                assert publication.branch_name.endswith(
                    "-2"
                )
                assert base_branch in bare_remote_branches(
                    workspace.bare_remote
                )
                assert publication.branch_name in bare_remote_branches(
                    workspace.bare_remote
                )
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_push_failure_retry_reuses_branch_and_commit():
    workspace = prepare_publishing_workspace()
    github = FakeGitHubPublisher()
    factory = FailingPushFactory(
        failures=1
    )
    service = publication_service(
        github=github,
        git_factory=factory,
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                first = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                assert first.status == FAILED
                assert first.commit_sha
                assert first.pull_request_number is None
                first_commit = first.commit_sha
                first_branch = first.branch_name

                second = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                assert second.status == PUBLISHED
                assert second.commit_sha == first_commit
                assert second.branch_name == first_branch
                assert len(github.created_requests) == 1
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_push_success_pr_failure_retry_reuses_commit_and_creates_one_pr():
    workspace = prepare_publishing_workspace()
    github = FakeGitHubPublisher()
    github.fail_create_once = True
    service = publication_service(
        github=github
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                first = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                assert first.status == PARTIALLY_PUBLISHED
                assert first.commit_sha
                assert first.pull_request_number is None
                first_commit = first.commit_sha
                first_branch = first.branch_name

                second = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                assert second.status == PUBLISHED
                assert second.commit_sha == first_commit
                assert second.branch_name == first_branch
                assert second.pull_request_number == 2
                assert len(github.open_prs) == 1
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_existing_pr_is_detected_on_retry_without_duplicate_creation():
    workspace = prepare_publishing_workspace()
    github = FakeGitHubPublisher()
    github.fail_create_once = True
    service = publication_service(
        github=github
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                first = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )
                github.open_prs.append(
                    fake_existing_pr(
                        branch_name=first.branch_name,
                    )
                )
                second = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )

                assert second.status == PUBLISHED
                assert second.pull_request_number == 77
                assert len(github.created_requests) == 1
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_credentials_are_redacted_and_not_written_to_remote_url():
    workspace = prepare_publishing_workspace()
    token = "ghp_secret_publish_token"
    factory = FailingPushFactory(
        failures=1,
        token_to_leak=token,
    )
    service = publication_service(
        git_factory=factory,
        authenticator=StaticAuthenticator(
            GitHubCredentials(
                username="x-access-token",
                token=token,
            )
        ),
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                publication = await service.publish_review(
                    review_id=workspace.review.id,
                    repository_path=workspace.repo,
                    db=db,
                )

                assert publication.status == FAILED
                assert token not in (
                    publication.error_message or ""
                )
                assert "[REDACTED]" in (
                    publication.error_message or ""
                )

            remote_config = run_git_capture(
                workspace.repo,
                [
                    "remote",
                    "-v",
                ],
            )
            assert token not in remote_config
        finally:
            await cleanup_publishing_workspace(
                workspace
            )

    asyncio.run(
        run_test()
    )


def test_pr_body_is_deterministic_and_preserves_skipped_statuses():
    workspace = prepare_publishing_workspace()

    try:
        body = build_pr_body(
            workspace.review
        )

        assert "Refs #142" in body
        assert "* Modified `src/components/SearchBox.tsx`" in body
        assert "* Tests: Passed" in body
        assert "* Lint: Skipped" in body
        assert "* Typecheck: Skipped" in body
        assert "* Build: Skipped" in body
        assert workspace.review.diff not in body
        assert build_commit_subject(
            workspace.review
        ).startswith(
            "Fix #142: "
        )
    finally:
        asyncio.run(
            cleanup_publishing_workspace(
                workspace
            )
        )


def publication_service(
    *,
    github: FakeGitHubPublisher | None = None,
    git_cls: type[SafeGitPublisher] = SafeGitPublisher,
    git_factory=None,
    authenticator: StaticAuthenticator | None = None,
) -> PublicationService:
    return PublicationService(
        github_publisher=github or FakeGitHubPublisher(),
        authenticator=authenticator or StaticAuthenticator(),
        git_factory=(
            git_factory
            or (
                lambda path: git_cls(
                    repository_path=path
                )
            )
        ),
    )


async def publication_count(
    db,
    review_id,
) -> int:
    return await db.scalar(
        select(
            func.count()
        )
        .select_from(Publication)
        .where(
            Publication.review_id == review_id
        )
    )


async def publication_for_review(
    db,
    review_id,
) -> Publication:
    publication = await db.scalar(
        select(Publication).where(
            Publication.review_id == review_id
        )
    )
    assert publication is not None
    return publication


class TamperingStageGitPublisher(SafeGitPublisher):
    def stage_files(
        self,
        paths: list[str],
    ) -> None:
        super().stage_files(
            paths
        )
        target = (
            self.repository_path
            / paths[0]
        )
        target.write_text(
            target.read_text(
                encoding="utf-8"
            )
            + "\n// tampered staged content\n",
            encoding="utf-8",
        )
        super().stage_files(
            [
                paths[0]
            ]
        )


class CommitDiffMismatchGitPublisher(SafeGitPublisher):
    def commit_diff(
        self,
        *,
        base_commit_sha: str,
        commit_sha: str,
    ) -> str:
        return (
            super().commit_diff(
                base_commit_sha=base_commit_sha,
                commit_sha=commit_sha,
            )
            + "\n+unexpected committed diff\n"
        )


class WrongParentGitPublisher(SafeGitPublisher):
    def commit_parent(
        self,
        commit_sha: str,
    ) -> str:
        return "0" * 40


class DefaultBranchPublicationService(PublicationService):
    def choose_publication_branch(
        self,
        *,
        review,
        base_branch: str,
        credentials,
        git,
    ) -> str:
        return base_branch


class FailingWorkingDiffOnceFactory:
    def __init__(self) -> None:
        self.failures = 1

    def __call__(
        self,
        path,
    ) -> SafeGitPublisher:
        return FailingWorkingDiffOnceGitPublisher(
            repository_path=path,
            factory=self,
        )


class FailingWorkingDiffOnceGitPublisher(
    SafeGitPublisher
):
    def __init__(
        self,
        *,
        repository_path,
        factory: FailingWorkingDiffOnceFactory,
    ) -> None:
        super().__init__(
            repository_path=repository_path
        )
        self.factory = factory

    def working_tree_diff(
        self,
    ) -> str:
        if self.factory.failures:
            self.factory.failures -= 1
            return ""

        return super().working_tree_diff()


class FailingPushFactory:
    def __init__(
        self,
        *,
        failures: int,
        token_to_leak: str | None = None,
    ) -> None:
        self.failures = failures
        self.token_to_leak = token_to_leak

    def __call__(
        self,
        path,
    ) -> SafeGitPublisher:
        return FailingPushGitPublisher(
            repository_path=path,
            factory=self,
        )


class FailingPushGitPublisher(SafeGitPublisher):
    def __init__(
        self,
        *,
        repository_path,
        factory: FailingPushFactory,
    ) -> None:
        super().__init__(
            repository_path=repository_path
        )
        self.factory = factory

    def push_branch(
        self,
        *,
        branch_name: str,
        credentials,
    ) -> None:
        if self.factory.failures:
            self.factory.failures -= 1
            leaked = (
                f" {self.factory.token_to_leak}"
                if self.factory.token_to_leak
                else ""
            )
            raise GitPushError(
                "remote rejected push" + leaked
            )

        super().push_branch(
            branch_name=branch_name,
            credentials=credentials,
        )


def fake_existing_pr(
    *,
    branch_name: str,
) -> PullRequestMetadata:
    return PullRequestMetadata(
        number=77,
        url=(
            "https://github.test/acme/storefront/pull/"
            f"{branch_name}"
        ),
        head_sha=None,
    )
