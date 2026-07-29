import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.change_set import (
    ChangeSet,
)
from app.db.models.execution_plan import (
    ExecutionPlan,
)
from app.db.models.execution_run import (
    ExecutionRun,
)
from app.db.models.final_review import (
    FinalReview,
)
from app.db.models.publication import (
    Publication,
)
from app.observability.logging import (
    log_task_event,
)
from app.services.changes.git import (
    GitCommandError,
)
from app.services.changes.hashing import (
    diff_hash,
)
from app.services.publishing.authentication import (
    GitHubAuthenticator,
    GitHubCredentials,
    SettingsGitHubAuthenticator,
)
from app.services.github.app_client import (
    GitHubAppClient,
    github_app_client,
)
from app.services.publishing.git import (
    GitPushError,
    SafeGitPublisher,
    sanitize_error,
)
from app.services.publishing.github import (
    GitHubApiPublisher,
    GitHubPublisher,
    GitHubPublisherError,
    PullRequestCreationError,
    PullRequestMetadata,
)
from app.services.publishing.integrity import (
    BranchCollisionError,
    CommitDiffMismatchError,
    CommitParentMismatchError,
    PublicationError,
    PublicationIntegrityError,
    PublicationStateError,
    RepositoryMismatchError,
    StagedDiffMismatchError,
    StagedFileMismatchError,
    assert_hash_matches,
    reviewed_file_paths,
    validate_publishable_review,
)
from app.services.publishing.naming import (
    BranchNameError,
    collision_branch_name,
    generate_branch_name,
    validate_branch_name,
)
from app.services.reviews.service import (
    PENDING_REVIEW,
    ReviewIntegrityError,
    ReviewService,
)
from app.services.tasks.failures import (
    GITHUB_PUBLISH_ERROR,
    GIT_ERROR,
)
from app.services.tasks.locking import (
    TaskOperationLockService,
)
from app.services.tasks.service import (
    TaskService,
)
from app.services.tasks.state_machine import (
    COMPLETED,
    FAILED as TASK_FAILED,
    PUBLISHING as TASK_PUBLISHING,
    REVIEW_APPROVED,
    REVIEW_PENDING,
    TaskTransitionError,
)


PENDING = "pending"
PUBLISHING = "publishing"
LOCAL_COMMITTED = "local_committed"
PUSHED = "pushed"
PUBLISHED = "published"
FAILED = "failed"
PARTIALLY_PUBLISHED = "partially_published"


class PublicationService:
    def __init__(
        self,
        *,
        review_service: ReviewService | None = None,
        git_factory: Callable[[Path], SafeGitPublisher]
        | None = None,
        github_publisher: GitHubPublisher | None = None,
        authenticator: GitHubAuthenticator | None = None,
        github_app: GitHubAppClient | None = None,
    ) -> None:
        self.review_service = (
            review_service or ReviewService()
        )
        self.git_factory = (
            git_factory
            or (
                lambda path: SafeGitPublisher(
                    repository_path=path
                )
            )
        )
        self.github_publisher = (
            github_publisher
            or GitHubApiPublisher()
        )
        self.authenticator = (
            authenticator
            or SettingsGitHubAuthenticator()
        )
        self.github_app = github_app or github_app_client

    async def publish_review(
        self,
        *,
        review_id: uuid.UUID,
        repository_path: Path,
        db: AsyncSession,
        task_id: uuid.UUID | None = None,
        github_installation_id: int | None = None,
        installation_id: uuid.UUID | None = None,
        repository_id: uuid.UUID | None = None,
    ) -> Publication:
        records = await self.load_review_records(
            review_id=review_id,
            db=db,
        )
        review, plan, change_set, execution_run = (
            records
        )
        task_id = (
            task_id
            or review.task_id
            or plan.task_id
            or change_set.task_id
            or execution_run.task_id
        )
        task_service = TaskService()
        lock_service = TaskOperationLockService()
        lock_acquired = False
        validate_publishable_review(
            review=review,
            plan=plan,
            change_set=change_set,
            execution_run=execution_run,
        )
        await self.review_service.require_final_change_set(
            change_set,
            db,
        )
        paths = reviewed_file_paths(
            review
        )
        git = self.git_factory(
            repository_path
        )
        if github_installation_id is not None:
            credentials = GitHubCredentials(
                username="x-access-token",
                token=(
                    await self.github_app.create_installation_token(
                        github_installation_id
                    )
                ),
            )
        else:
            credentials = await self.authenticator.get_credentials(
                owner=plan.repository_owner,
                repo=plan.repository_name,
            )
        repository_metadata = await self.github_publisher.get_repository(
            owner=plan.repository_owner,
            repo=plan.repository_name,
            credentials=credentials,
        )
        publication = await self.get_publication_by_review(
            review_id=review.id,
            db=db,
        )
        is_retry = (
            publication is not None
            and publication.status != PUBLISHED
        )
        previous_publication_status = (
            publication.status
            if publication is not None
            else None
        )

        if publication is None:
            try:
                await self.review_service.revalidate_review_integrity(
                    review=review,
                    repository_path=repository_path,
                    db=db,
                )
            except ReviewIntegrityError:
                await self.invalidate_review_approval(
                    review=review,
                    task_id=task_id,
                    db=db,
                )
                raise
            publication = await self.create_publication(
                review=review,
                plan=plan,
                change_set=change_set,
                base_branch=repository_metadata.default_branch,
                db=db,
                installation_id=installation_id,
                repository_id=repository_id,
            )
        else:
            validate_existing_publication(
                publication=publication,
                review=review,
                plan=plan,
            )
            if publication.status == PUBLISHED:
                validate_published_publication(
                    publication
                )
                if task_id is not None:
                    try:
                        await task_service.transition_task(
                            task_id=task_id,
                            new_status=TASK_PUBLISHING,
                            db=db,
                            event_type="publication.found",
                            publication_id=publication.id,
                            metadata={
                                "publication_id": str(
                                    publication.id
                                )
                            },
                        )
                        await task_service.transition_task(
                            task_id=task_id,
                            new_status=COMPLETED,
                            db=db,
                            event_type="publication.completed",
                            publication_id=publication.id,
                            metadata={
                                "publication_id": str(
                                    publication.id
                                ),
                                "pull_request_url": (
                                    publication.pull_request_url
                                ),
                            },
                        )
                    except TaskTransitionError:
                        await task_service.record_event(
                            task_id=task_id,
                            event_type="publication.already_completed",
                            db=db,
                            metadata={
                                "publication_id": str(
                                    publication.id
                                )
                            },
                            commit=True,
                        )
                return publication

            publication.retry_count += 1
            publication.publication_attempt_id = uuid.uuid4()
            publication.error_message = None
            if publication.base_branch is None:
                publication.base_branch = (
                    repository_metadata.default_branch
                )
            await self.save_publication(
                publication,
                db,
            )

        try:
            if task_id is not None:
                await lock_service.acquire(
                    task_id=task_id,
                    operation="publishing",
                    db=db,
                )
                lock_acquired = True
                task = await task_service.require_task(
                    task_id=task_id,
                    db=db,
                )
                retrying_failed_task = (
                    is_retry
                    and task.status == TASK_FAILED
                )
                log_task_event(
                    "publication.attempt_started",
                    task_id=str(task_id),
                    review_id=str(review.id),
                    publication_id=str(publication.id),
                    retry=is_retry,
                    retry_count=publication.retry_count,
                    previous_publication_status=(
                        previous_publication_status
                    ),
                    previous_task_status=task.status,
                )
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=TASK_PUBLISHING,
                    db=db,
                    event_type="publication.started",
                    active_review_id=review.id,
                    publication_id=publication.id,
                    metadata={
                        "review_id": str(review.id),
                        "publication_id": str(
                            publication.id
                        ),
                    },
                    allow_reconcile=retrying_failed_task,
                    clear_failure=retrying_failed_task,
                )

            publication = await self.continue_publication(
                publication=publication,
                review=review,
                plan=plan,
                paths=paths,
                repository_path=repository_path,
                base_branch=repository_metadata.default_branch,
                credentials=credentials,
                git=git,
                db=db,
            )
            if task_id is not None:
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=COMPLETED,
                    db=db,
                    event_type="publication.completed",
                    publication_id=publication.id,
                    metadata={
                        "publication_id": str(
                            publication.id
                        ),
                        "commit_sha": (
                            publication.commit_sha
                        ),
                        "pull_request_url": (
                            publication.pull_request_url
                        ),
                    },
                )
            return publication
        except (
            GitHubPublisherError,
            PullRequestCreationError,
        ) as exc:
            publication.status = PARTIALLY_PUBLISHED
            publication.failure_stage = "pull_request"
            publication.failure_reason = exc.__class__.__name__
            publication.error_message = safe_public_error(
                str(exc),
                credentials,
            )
            await self.save_publication(
                publication,
                db,
            )
            if task_id is not None:
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=TASK_PUBLISHING,
                    db=db,
                    event_type="publication.partially_published",
                    failure_category=GITHUB_PUBLISH_ERROR,
                    last_error=str(exc),
                    publication_id=publication.id,
                    metadata={
                        "publication_id": str(
                            publication.id
                        ),
                        "status": publication.status,
                    },
                )
            return publication
        except GitPushError as exc:
            publication.status = FAILED
            publication.failure_stage = "push"
            publication.failure_reason = exc.__class__.__name__
            publication.error_message = safe_public_error(
                str(exc),
                credentials,
            )
            await self.save_publication(
                publication,
                db,
            )
            if task_id is not None:
                await task_service.set_failure(
                    task_id=task_id,
                    db=db,
                    failure_category=GIT_ERROR,
                    error=exc,
                    event_type="publication.failed",
                    metadata={
                        "publication_id": str(
                            publication.id
                        )
                    },
                )
            return publication
        except (
            BranchNameError,
            GitCommandError,
            PublicationError,
        ) as exc:
            publication.status = FAILED
            publication.failure_stage = "integrity"
            publication.failure_reason = exc.__class__.__name__
            publication.error_message = safe_public_error(
                str(exc),
                credentials,
            )
            await self.save_publication(
                publication,
                db,
            )
            if task_id is not None:
                await task_service.set_failure(
                    task_id=task_id,
                    db=db,
                    failure_category=GITHUB_PUBLISH_ERROR,
                    error=exc,
                    event_type="publication.failed",
                    metadata={
                        "publication_id": str(
                            publication.id
                        )
                    },
                )
            raise
        finally:
            if lock_acquired and task_id is not None:
                await lock_service.release(
                    task_id=task_id,
                    operation="publishing",
                    db=db,
                )

    async def invalidate_review_approval(
        self,
        *,
        review: FinalReview,
        task_id: uuid.UUID | None,
        db: AsyncSession,
    ) -> None:
        review.status = PENDING_REVIEW
        review.decision = None
        review.reviewed_at = None
        review.reviewed_by = None
        review.reviewed_by_user_id = None
        await db.commit()
        await db.refresh(review)
        if task_id is None:
            return
        task_service = TaskService()
        task = await task_service.get_task(
            task_id=task_id,
            db=db,
        )
        if task is not None and task.status == REVIEW_APPROVED:
            await task_service.transition_task(
                task_id=task_id,
                new_status=REVIEW_PENDING,
                db=db,
                event_type="review.approval_invalidated",
                active_review_id=review.id,
                metadata={
                    "review_id": str(review.id),
                    "reason": "diff_integrity_changed",
                },
            )

    async def continue_publication(
        self,
        *,
        publication: Publication,
        review: FinalReview,
        plan: ExecutionPlan,
        paths: list[str],
        repository_path: Path,
        base_branch: str,
        credentials: GitHubCredentials | None,
        git: SafeGitPublisher,
        db: AsyncSession,
    ) -> Publication:
        publication.base_branch = base_branch
        validate_branch_name(
            publication.branch_name
            or generated_branch_name(
                review
            ),
            base_branch=base_branch,
        )

        if publication.commit_sha is None:
            await self.prepare_commit(
                publication=publication,
                review=review,
                plan=plan,
                paths=paths,
                repository_path=repository_path,
                base_branch=base_branch,
                credentials=credentials,
                git=git,
                db=db,
            )
        else:
            await self.verify_existing_commit(
                publication=publication,
                review=review,
                git=git,
                db=db,
            )

        await self.push_publication_branch(
            publication=publication,
            review=review,
            plan=plan,
            credentials=credentials,
            git=git,
            db=db,
        )
        await self.create_or_record_pull_request(
            publication=publication,
            review=review,
            plan=plan,
            credentials=credentials,
            db=db,
        )

        publication.status = PUBLISHED
        publication.error_message = None
        publication.published_at = now_utc()
        await self.save_publication(
            publication,
            db,
        )

        return publication

    async def prepare_commit(
        self,
        *,
        publication: Publication,
        review: FinalReview,
        plan: ExecutionPlan,
        paths: list[str],
        repository_path: Path,
        base_branch: str,
        credentials: GitHubCredentials | None,
        git: SafeGitPublisher,
        db: AsyncSession,
    ) -> None:
        await self.review_service.revalidate_review_integrity(
            review=review,
            repository_path=repository_path,
            db=db,
        )
        current_head = git.current_head()

        if current_head != review.base_commit_sha:
            raise PublicationIntegrityError(
                "Current HEAD does not match approved review base"
            )

        working_hash = diff_hash(
            git.working_tree_diff()
        )
        log_task_event(
            "publication.working_diff_checked",
            task_id=(
                str(publication.task_id)
                if publication.task_id
                else None
            ),
            review_id=str(review.id),
            publication_id=str(publication.id),
            actual_diff_hash=working_hash,
            expected_diff_hash=review.diff_hash,
            matches=(
                working_hash
                == review.diff_hash
            ),
        )
        assert_hash_matches(
            actual=working_hash,
            expected=review.diff_hash,
            message="Working tree diff does not match approved review diff",
        )
        publication.working_tree_diff_hash = (
            working_hash
        )

        if publication.branch_name is None:
            publication.branch_name = (
                self.choose_publication_branch(
                    review=review,
                    base_branch=base_branch,
                    credentials=credentials,
                    git=git,
                )
            )

        validate_branch_name(
            publication.branch_name,
            base_branch=base_branch,
        )
        publication.status = PUBLISHING
        await self.save_publication(
            publication,
            db,
        )
        git.switch_or_create_branch(
            publication.branch_name
        )

        branch_working_hash = diff_hash(
            git.working_tree_diff()
        )
        log_task_event(
            "publication.branch_diff_checked",
            task_id=(
                str(publication.task_id)
                if publication.task_id
                else None
            ),
            review_id=str(review.id),
            publication_id=str(publication.id),
            actual_diff_hash=branch_working_hash,
            expected_diff_hash=review.diff_hash,
            matches=(
                branch_working_hash
                == review.diff_hash
            ),
        )
        assert_hash_matches(
            actual=branch_working_hash,
            expected=review.diff_hash,
            message="Branch creation changed the approved working diff",
        )
        publication.working_tree_diff_hash = (
            branch_working_hash
        )
        await self.stage_and_validate(
            publication=publication,
            review=review,
            paths=paths,
            git=git,
            db=db,
        )
        commit_sha = git.commit(
            subject=build_commit_subject(
                review
            ),
            body=build_commit_body(
                review
            ),
        )
        publication.commit_sha = commit_sha
        publication.status = LOCAL_COMMITTED
        await self.save_publication(
            publication,
            db,
        )
        await self.verify_existing_commit(
            publication=publication,
            review=review,
            git=git,
            db=db,
        )

    async def stage_and_validate(
        self,
        *,
        publication: Publication,
        review: FinalReview,
        paths: list[str],
        git: SafeGitPublisher,
        db: AsyncSession,
    ) -> None:
        git.stage_files(
            paths
        )
        staged_files = sorted(
            git.staged_files()
        )

        if staged_files != paths:
            git.unstage_files(
                staged_files
            )
            raise StagedFileMismatchError(
                "Staged files do not exactly match approved review files"
            )

        staged_hash = diff_hash(
            git.staged_diff()
        )
        publication.staged_diff_hash = (
            staged_hash
        )
        await self.save_publication(
            publication,
            db,
        )

        if staged_hash != review.diff_hash:
            git.unstage_files(
                git.staged_files()
            )
            raise StagedDiffMismatchError(
                "Staged diff does not match approved review diff"
            )

    async def verify_existing_commit(
        self,
        *,
        publication: Publication,
        review: FinalReview,
        git: SafeGitPublisher,
        db: AsyncSession,
    ) -> None:
        if publication.commit_sha is None:
            raise PublicationStateError(
                "Publication has no commit to verify"
            )

        parent_sha = git.commit_parent(
            publication.commit_sha
        )

        if parent_sha != review.base_commit_sha:
            raise CommitParentMismatchError(
                "Publication commit parent does not match approved base"
            )

        committed_hash = diff_hash(
            git.commit_diff(
                base_commit_sha=review.base_commit_sha,
                commit_sha=publication.commit_sha,
            )
        )
        publication.commit_diff_hash = (
            committed_hash
        )
        await self.save_publication(
            publication,
            db,
        )
        assert_hash_matches(
            actual=committed_hash,
            expected=review.diff_hash,
            message="Committed diff does not match approved review diff",
            error_type=CommitDiffMismatchError,
        )

    async def push_publication_branch(
        self,
        *,
        publication: Publication,
        review: FinalReview,
        plan: ExecutionPlan,
        credentials: GitHubCredentials | None,
        git: SafeGitPublisher,
        db: AsyncSession,
    ) -> None:
        if (
            publication.branch_name is None
            or publication.commit_sha is None
        ):
            raise PublicationStateError(
                "Publication branch and commit are required before push"
            )

        validate_branch_name(
            publication.branch_name,
            base_branch=publication.base_branch
            or "",
        )
        git.push_branch(
            branch_name=publication.branch_name,
            credentials=credentials,
        )
        remote_sha = git.remote_branch_sha(
            publication.branch_name,
            credentials=credentials,
        )

        if remote_sha != publication.commit_sha:
            raise PublicationIntegrityError(
                "Remote branch HEAD does not match publication commit"
            )

        publication.remote_head_sha = remote_sha
        publication.remote_branch_created_at = (
            publication.remote_branch_created_at
            or now_utc()
        )
        publication.status = PUSHED
        await self.save_publication(
            publication,
            db,
        )

    async def create_or_record_pull_request(
        self,
        *,
        publication: Publication,
        review: FinalReview,
        plan: ExecutionPlan,
        credentials: GitHubCredentials | None,
        db: AsyncSession,
    ) -> None:
        if (
            publication.branch_name is None
            or publication.commit_sha is None
            or publication.base_branch is None
        ):
            raise PublicationStateError(
                "Publication is missing PR inputs"
            )

        existing = await self.github_publisher.find_open_pull_request(
            owner=plan.repository_owner,
            repo=plan.repository_name,
            head_branch=publication.branch_name,
            base_branch=publication.base_branch,
            credentials=credentials,
        )

        if existing is None:
            existing = await self.github_publisher.create_pull_request(
                owner=plan.repository_owner,
                repo=plan.repository_name,
                head_branch=publication.branch_name,
                base_branch=publication.base_branch,
                title=build_pr_title(
                    review
                ),
                body=build_pr_body(
                    review
                ),
                credentials=credentials,
            )

        validate_pull_request_head(
            pull_request=existing,
            publication=publication,
        )
        publication.pull_request_number = (
            existing.number
        )
        publication.pull_request_url = existing.url
        publication.pr_created_at = (
            publication.pr_created_at
            or now_utc()
        )

    def choose_publication_branch(
        self,
        *,
        review: FinalReview,
        base_branch: str,
        credentials: GitHubCredentials | None,
        git: SafeGitPublisher,
    ) -> str:
        branch = generated_branch_name(
            review
        )

        for attempt in range(
            1,
            21,
        ):
            candidate = (
                branch
                if attempt == 1
                else collision_branch_name(
                    base_branch_name=branch,
                    attempt=attempt,
                )
            )
            validate_branch_name(
                candidate,
                base_branch=base_branch,
            )
            remote_sha = git.remote_branch_sha(
                candidate,
                credentials=credentials,
            )

            if (
                remote_sha is None
                and not git.local_branch_exists(
                    candidate
                )
            ):
                return candidate

        raise BranchCollisionError(
            "Could not find an available RepoPilot branch name"
        )

    async def load_review_records(
        self,
        *,
        review_id: uuid.UUID,
        db: AsyncSession,
    ) -> tuple[
        FinalReview,
        ExecutionPlan,
        ChangeSet,
        ExecutionRun,
    ]:
        review = await self.review_service.load_review(
            review_id,
            db,
        )
        plan = await self.review_service.load_plan(
            review.plan_id,
            db,
        )
        change_set = await self.review_service.load_change_set(
            review.change_set_id,
            db,
        )
        execution_run = await self.review_service.load_execution_run(
            review.execution_run_id,
            db,
        )

        return (
            review,
            plan,
            change_set,
            execution_run,
        )

    async def get_publication(
        self,
        *,
        publication_id: uuid.UUID,
        db: AsyncSession,
    ) -> Publication | None:
        return await db.get(
            Publication,
            publication_id,
        )

    async def get_publication_by_review(
        self,
        *,
        review_id: uuid.UUID,
        db: AsyncSession,
    ) -> Publication | None:
        result = await db.scalars(
            select(Publication)
            .where(
                Publication.review_id == review_id
            )
            .limit(1)
        )

        return result.first()

    async def create_publication(
        self,
        *,
        review: FinalReview,
        plan: ExecutionPlan,
        change_set: ChangeSet,
        base_branch: str,
        db: AsyncSession,
        installation_id: uuid.UUID | None = None,
        repository_id: uuid.UUID | None = None,
    ) -> Publication:
        publication = Publication(
            workspace_id=review.workspace_id,
            task_id=(
                review.task_id
                or plan.task_id
                or change_set.task_id
            ),
            review_id=review.id,
            plan_id=plan.id,
            change_set_id=change_set.id,
            status=PENDING,
            repository_owner=plan.repository_owner,
            repository_name=plan.repository_name,
            base_branch=base_branch,
            base_commit_sha=review.base_commit_sha,
            approved_diff_hash=review.diff_hash,
            installation_id=installation_id,
            repository_id=repository_id,
            publication_attempt_id=uuid.uuid4(),
        )
        db.add(
            publication
        )

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await self.get_publication_by_review(
                review_id=review.id,
                db=db,
            )
            if existing is None:
                raise
            return existing

        await db.refresh(
            publication
        )
        return publication

    async def save_publication(
        self,
        publication: Publication,
        db: AsyncSession,
    ) -> None:
        await db.commit()
        await db.refresh(
            publication
        )


def generated_branch_name(
    review: FinalReview,
) -> str:
    issue_number = int(
        (review.issue_json or {}).get(
            "issue_number",
            0,
        )
    )

    return generate_branch_name(
        issue_number=issue_number,
        summary=review.summary or "change",
        diff_hash=review.diff_hash,
    )


def validate_existing_publication(
    *,
    publication: Publication,
    review: FinalReview,
    plan: ExecutionPlan,
) -> None:
    if (
        publication.workspace_id != review.workspace_id
        or publication.plan_id != review.plan_id
        or publication.change_set_id
        != review.change_set_id
        or publication.base_commit_sha
        != review.base_commit_sha
        or publication.approved_diff_hash
        != review.diff_hash
        or publication.repository_owner
        != plan.repository_owner
        or publication.repository_name
        != plan.repository_name
    ):
        raise RepositoryMismatchError(
            "Publication no longer matches its reviewed repository chain"
        )


def validate_published_publication(
    publication: Publication,
) -> None:
    if (
        publication.branch_name is None
        or publication.commit_sha is None
        or publication.pull_request_number is None
        or publication.pull_request_url is None
    ):
        raise PublicationStateError(
            "Published Publication is missing required metadata"
        )


def validate_pull_request_head(
    *,
    pull_request: PullRequestMetadata,
    publication: Publication,
) -> None:
    if (
        pull_request.head_sha is not None
        and pull_request.head_sha != publication.commit_sha
    ):
        raise PublicationIntegrityError(
            "Pull Request head SHA does not match publication commit"
        )


def build_commit_subject(
    review: FinalReview,
) -> str:
    issue_number = (
        review.issue_json or {}
    ).get(
        "issue_number"
    )
    prefix = (
        f"Fix #{issue_number}: "
        if issue_number
        else "RepoPilot: "
    )
    summary = sanitize_inline_text(
        review.summary or "publish reviewed change"
    )
    max_summary_length = 72 - len(
        prefix
    )

    return (
        prefix + summary[:max_summary_length]
    ).rstrip(" .")


def build_commit_body(
    review: FinalReview,
) -> str:
    issue_number = (
        review.issue_json or {}
    ).get(
        "issue_number"
    )
    lines = [
        sanitize_inline_text(
            review.summary or "Reviewed RepoPilot change."
        ),
        "",
    ]

    if issue_number:
        lines.extend(
            [
                f"Refs #{issue_number}",
                "",
            ]
        )

    lines.extend(
        [
            "RepoPilot publication:",
            f"- Review: {review.id}",
            f"- ChangeSet: {review.change_set_id}",
            f"- Reviewed diff hash: {review.diff_hash}",
            "- Final diff approved by human",
        ]
    )

    return "\n".join(
        lines
    )


def build_pr_title(
    review: FinalReview,
) -> str:
    return build_commit_subject(
        review
    )


def build_pr_body(
    review: FinalReview,
) -> str:
    issue_number = (
        review.issue_json or {}
    ).get(
        "issue_number"
    )
    debug_attempts = (
        review.debug_history_json or {}
    ).get(
        "debug_attempts",
        0,
    )
    checks = (
        review.verification_json or {}
    ).get(
        "checks",
        {},
    )
    file_lines = [
        f"* {change_label(file)} `{file['path']}`"
        for file in review.files_json
    ]
    lines = [
        "## Summary",
        sanitize_inline_text(
            review.summary or "Reviewed RepoPilot change."
        ),
        "",
        "## Issue",
        (
            f"Refs #{issue_number}"
            if issue_number
            else "No linked issue number."
        ),
        "",
        "## Changes",
        *file_lines,
        "",
        "## Verification",
        f"* Tests: {format_status(checks.get('tests'))}",
        f"* Typecheck: {format_status(checks.get('typecheck'))}",
        f"* Lint: {format_status(checks.get('lint'))}",
        f"* Build: {format_status(checks.get('build'))}",
        "",
        "## RepoPilot Execution",
        "* Plan approved by human",
        "* Final diff approved by human",
        f"* Debug attempts: {debug_attempts}",
        f"* Files changed: {review.files_changed}",
        f"* Lines added: {review.lines_added}",
        f"* Lines removed: {review.lines_deleted}",
    ]

    return "\n".join(
        lines
    )


def change_label(
    file: dict,
) -> str:
    value = sanitize_inline_text(
        str(
            file.get(
                "change_type",
                "modified",
            )
        )
    )

    return value.capitalize()


def format_status(
    status: str | None,
) -> str:
    if status is None:
        return "Skipped"

    normalized = status.lower()
    labels = {
        "pass": "Passed",
        "passed": "Passed",
        "fail": "Failed",
        "failed": "Failed",
        "timeout": "Timed out",
        "error": "Error",
        "skipped": "Skipped",
    }

    return labels.get(
        normalized,
        sanitize_inline_text(status).capitalize(),
    )


def sanitize_inline_text(
    value: str,
) -> str:
    cleaned = " ".join(
        value.replace(
            "\x00",
            "",
        ).split()
    )

    return cleaned[:300]


def safe_public_error(
    message: str,
    credentials: GitHubCredentials | None,
) -> str:
    return sanitize_error(
        sanitize_inline_text(
            message
        ),
        secrets=(
            (credentials.token,)
            if credentials
            else ()
        ),
    )


def now_utc() -> datetime:
    return datetime.now(
        UTC
    )


def serialize_publication(
    publication: Publication,
) -> dict:
    return {
        "publication_id": str(
            publication.id
        ),
        "review_id": str(
            publication.review_id
        ),
        "workspace_id": (
            publication.workspace_id
        ),
        "plan_id": str(
            publication.plan_id
        ),
        "change_set_id": str(
            publication.change_set_id
        ),
        "status": publication.status,
        "repository": {
            "owner": publication.repository_owner,
            "name": publication.repository_name,
        },
        "base_branch": publication.base_branch,
        "head_branch": publication.branch_name,
        "base_commit_sha": (
            publication.base_commit_sha
        ),
        "approved_diff_hash": (
            publication.approved_diff_hash
        ),
        "working_tree_diff_hash": (
            publication.working_tree_diff_hash
        ),
        "staged_diff_hash": (
            publication.staged_diff_hash
        ),
        "commit_diff_hash": (
            publication.commit_diff_hash
        ),
        "commit_sha": publication.commit_sha,
        "remote_head_sha": (
            publication.remote_head_sha
        ),
        "pull_request_number": (
            publication.pull_request_number
        ),
        "pull_request_url": (
            publication.pull_request_url
        ),
        "retry_count": publication.retry_count,
        "error_message": (
            publication.error_message
        ),
        "failure_stage": publication.failure_stage,
        "failure_reason": publication.failure_reason,
        "created_at": isoformat(
            publication.created_at
        ),
        "updated_at": isoformat(
            publication.updated_at
        ),
        "remote_branch_created_at": isoformat(
            publication.remote_branch_created_at
        ),
        "pr_created_at": isoformat(
            publication.pr_created_at
        ),
        "published_at": isoformat(
            publication.published_at
        ),
    }


def isoformat(
    value,
) -> str | None:
    if value is None:
        return None

    return value.isoformat()
