import asyncio
import shutil
import subprocess
import uuid
from pathlib import Path

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.models.change_set import (
    ChangeSet,
)
from app.db.models.execution_run import (
    ExecutionRun,
)
from app.db.models.final_review import (
    FinalReview,
)
from app.db.session import (
    AsyncSessionLocal,
    engine,
)
from app.services.publishing.authentication import (
    GitHubCredentials,
)
from app.services.publishing.github import (
    PullRequestCreationError,
    PullRequestMetadata,
    RepositoryMetadata,
)
from app.services.reviews.service import (
    ReviewService,
)
from app.services.sandbox.results import (
    EXECUTION_PASSED,
    STATUS_PASS,
)
from tests.coding_fixtures import (
    run_git,
)
from tests.debugging_fixtures import (
    seed_execution_run,
)
from tests.execution_fixtures import (
    cleanup_execution_workspace,
    create_node_execution_fixture_repo,
    seed_generated_change_set,
)


class PublishingWorkspace:
    def __init__(
        self,
        *,
        workspace_id: str,
        workspace_path: Path,
        repo: Path,
        bare_remote: Path,
        change_set: ChangeSet,
        execution_run: ExecutionRun,
        review: FinalReview,
    ) -> None:
        self.workspace_id = workspace_id
        self.workspace_path = workspace_path
        self.repo = repo
        self.bare_remote = bare_remote
        self.change_set = change_set
        self.execution_run = execution_run
        self.review = review


class FakeGitHubPublisher:
    def __init__(
        self,
        *,
        default_branch: str = "main",
    ) -> None:
        self.default_branch = default_branch
        self.repository_requests: list[tuple[str, str]] = []
        self.find_requests: list[dict] = []
        self.created_requests: list[dict] = []
        self.open_prs: list[PullRequestMetadata] = []
        self.fail_create_once = False
        self.next_head_sha: str | None = None

    async def get_repository(
        self,
        *,
        owner: str,
        repo: str,
        credentials,
    ) -> RepositoryMetadata:
        self.repository_requests.append(
            (
                owner,
                repo,
            )
        )
        return RepositoryMetadata(
            default_branch=self.default_branch
        )

    async def find_open_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str,
        credentials,
    ) -> PullRequestMetadata | None:
        self.find_requests.append(
            {
                "owner": owner,
                "repo": repo,
                "head": head_branch,
                "base": base_branch,
            }
        )

        for pull_request in self.open_prs:
            if pull_request.url.endswith(
                f"/{head_branch}"
            ):
                return pull_request

        return None

    async def create_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        credentials,
    ) -> PullRequestMetadata:
        self.created_requests.append(
            {
                "owner": owner,
                "repo": repo,
                "head": head_branch,
                "base": base_branch,
                "title": title,
                "body": body,
            }
        )

        if self.fail_create_once:
            self.fail_create_once = False
            raise PullRequestCreationError(
                "GitHub PR creation failed"
            )

        pull_request = PullRequestMetadata(
            number=len(
                self.created_requests
            ),
            url=(
                "https://github.test/"
                f"{owner}/{repo}/pull/{head_branch}"
            ),
            head_sha=self.next_head_sha,
        )
        self.open_prs.append(
            pull_request
        )

        return pull_request


class StaticAuthenticator:
    def __init__(
        self,
        credentials: GitHubCredentials | None = None,
    ) -> None:
        self.credentials = credentials
        self.calls: list[tuple[str, str]] = []

    async def get_credentials(
        self,
        *,
        owner: str,
        repo: str,
    ) -> GitHubCredentials | None:
        self.calls.append(
            (
                owner,
                repo,
            )
        )
        return self.credentials


def prepare_publishing_workspace() -> PublishingWorkspace:
    workspace_id = str(
        uuid.uuid4()
    )
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    bare_remote = workspace_path / "remote.git"
    create_node_execution_fixture_repo(
        repo
    )
    init_bare_remote(
        repo=repo,
        bare_remote=bare_remote,
    )

    async def seed_records():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        async with AsyncSessionLocal() as db:
            execution_run = await seed_execution_run(
                db=db,
                workspace_id=workspace_id,
                change_set_id=change_set.id,
                status=EXECUTION_PASSED,
                result_status=STATUS_PASS,
                stdout="PASS SearchBox\n",
            )
            service = ReviewService()
            review = await service.create_review(
                change_set_id=change_set.id,
                repository_path=repo,
                db=db,
            )
            approved = await service.approve_review(
                review_id=review.id,
                repository_path=repo,
                db=db,
            )

        await engine.dispose()

        return (
            change_set,
            execution_run,
            approved,
        )

    change_set, execution_run, review = asyncio.run(
        seed_records()
    )

    return PublishingWorkspace(
        workspace_id=workspace_id,
        workspace_path=workspace_path,
        repo=repo,
        bare_remote=bare_remote,
        change_set=change_set,
        execution_run=execution_run,
        review=review,
    )


def init_bare_remote(
    *,
    repo: Path,
    bare_remote: Path,
) -> None:
    subprocess.run(
        [
            "git",
            "init",
            "--bare",
            str(bare_remote),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(
        repo,
        [
            "branch",
            "-M",
            "main",
        ],
    )
    run_git(
        repo,
        [
            "remote",
            "add",
            "origin",
            str(bare_remote),
        ],
    )
    run_git(
        repo,
        [
            "push",
            "origin",
            "HEAD:main",
        ],
    )


async def cleanup_publishing_workspace(
    workspace: PublishingWorkspace,
) -> None:
    await cleanup_execution_workspace(
        workspace.workspace_id
    )
    await engine.dispose()
    shutil.rmtree(
        workspace.workspace_path,
        ignore_errors=True,
    )


def run_git_capture(
    repo: Path,
    args: list[str],
) -> str:
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


def bare_remote_branch_sha(
    bare_remote: Path,
    branch_name: str,
) -> str:
    result = subprocess.run(
        [
            "git",
            "--git-dir",
            str(bare_remote),
            "rev-parse",
            f"refs/heads/{branch_name}",
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    return result.stdout.strip()


def bare_remote_branches(
    bare_remote: Path,
) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "--git-dir",
            str(bare_remote),
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    return [
        line
        for line in result.stdout.splitlines()
        if line
    ]
