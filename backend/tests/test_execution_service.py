import asyncio
import hashlib
import uuid
from pathlib import Path

import pytest

from app.db.models.execution_run import (
    ExecutionRun,
)
from app.db.session import (
    AsyncSessionLocal,
    engine,
)
from app.services.sandbox.manager import (
    ExecutionService,
)
from app.services.sandbox.policy import (
    InvalidChangeSetStateError,
    WorkspaceStateMismatchError,
)
from app.services.sandbox.results import (
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
)
from tests.execution_fixtures import (
    FakeSandbox,
    cleanup_execution_workspace,
    create_node_execution_fixture_repo,
    seed_generated_change_set,
)
from tests.coding_fixtures import (
    run_git,
    write_file,
)


def file_hash(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


async def dispose_database_engine() -> None:
    await engine.dispose()


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "generating",
        "validation_failed",
        "failed",
    ],
)
def test_only_generated_changesets_can_execute(
    tmp_path: Path,
    status: str,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
            status=status,
        )

        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    InvalidChangeSetStateError
                ):
                    await ExecutionService(
                        sandbox=FakeSandbox(
                            sandbox_root=tmp_path
                            / "sandboxes"
                        )
                    ).execute_change_set(
                        change_set_id=change_set.id,
                        repository_path=repo,
                        db=db,
                    )
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_workspace_mismatch_rejects_execution(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )
        (
            repo / "src/components/SearchBox.tsx"
        ).write_text(
            "stale different patch\n",
            encoding="utf-8",
        )

        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    WorkspaceStateMismatchError
                ):
                    await ExecutionService(
                        sandbox=FakeSandbox(
                            sandbox_root=tmp_path
                            / "sandboxes"
                        )
                    ).execute_change_set(
                        change_set_id=change_set.id,
                        repository_path=repo,
                        db=db,
                    )
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_unapproved_untracked_file_rejects_execution(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )
        (
            repo / "unexpected.txt"
        ).write_text(
            "not in the recorded change set\n",
            encoding="utf-8",
        )

        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(
                    WorkspaceStateMismatchError,
                    match=(
                        "changed files do not match"
                    ),
                ):
                    await ExecutionService(
                        sandbox=FakeSandbox(
                            sandbox_root=tmp_path
                            / "sandboxes"
                        )
                    ).execute_change_set(
                        change_set_id=change_set.id,
                        repository_path=repo,
                        db=db,
                    )
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_approved_new_file_can_be_verified(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)
    (
        repo / "test.txt"
    ).write_text(
        "new file created by the approved plan\n",
        encoding="utf-8",
    )
    sandbox = FakeSandbox(
        sandbox_root=tmp_path / "sandboxes"
    )

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        try:
            async with AsyncSessionLocal() as db:
                run = await ExecutionService(
                    sandbox=sandbox
                ).execute_change_set(
                    change_set_id=change_set.id,
                    repository_path=repo,
                    db=db,
                )

                assert run.status == "passed"
                assert any(
                    file.path == "test.txt"
                    and file.before_sha256
                    == hashlib.sha256(b"").hexdigest()
                    for file in change_set.files
                )
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_plain_text_repository_without_commands_passes_as_skipped(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(
        repo,
        ["init", "-q"],
    )
    write_file(
        repo,
        "age.txt",
        "1\n",
    )
    run_git(
        repo,
        ["add", "age.txt"],
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
            "initial fixture",
            "-q",
        ],
    )
    write_file(
        repo,
        "test.txt",
        "new file created by the approved plan\n",
    )
    sandbox = FakeSandbox(
        sandbox_root=tmp_path / "sandboxes"
    )

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        try:
            async with AsyncSessionLocal() as db:
                run = await ExecutionService(
                    sandbox=sandbox
                ).execute_change_set(
                    change_set_id=change_set.id,
                    repository_path=repo,
                    db=db,
                )

                assert run.status == "passed"
                assert run.commands_json == []
                assert sandbox.executed == []
                assert run.runtime_metadata[
                    "verification_mode"
                ] == "skipped"
                assert run.runtime_metadata[
                    "verification_reason"
                ]
                assert {
                    result["status"]
                    for result in run.results_json
                } == {
                    STATUS_SKIPPED
                }
                assert run.tests_status == STATUS_SKIPPED
                assert run.typecheck_status == STATUS_SKIPPED
                assert run.lint_status == STATUS_SKIPPED
                assert run.build_status == STATUS_SKIPPED
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_successful_execution_persists_run_and_keeps_canonical_workspace_unchanged(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)
    changed_file = (
        repo / "src/components/SearchBox.tsx"
    )
    before_hash = file_hash(changed_file)
    sandbox = FakeSandbox(
        sandbox_root=tmp_path / "sandboxes",
        mutate_sandbox=True,
    )

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        try:
            async with AsyncSessionLocal() as db:
                run = await ExecutionService(
                    sandbox=sandbox
                ).execute_change_set(
                    change_set_id=change_set.id,
                    repository_path=repo,
                    db=db,
                )

                assert run.status == "passed"
                assert run.tests_status == STATUS_PASS
                assert run.typecheck_status == STATUS_PASS
                assert run.lint_status == STATUS_PASS
                assert run.build_status == STATUS_PASS
                assert run.results_json

                saved = await db.get(
                    ExecutionRun,
                    run.id,
                )
                assert saved is not None
                assert saved.status == "passed"

            assert file_hash(changed_file) == before_hash
            assert sandbox.cleanup_called is True
            assert sandbox.last_handle is not None
            assert not sandbox.last_handle.run_directory.exists()
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_failed_test_is_persisted_without_canonical_mutation(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)
    changed_file = (
        repo / "src/components/SearchBox.tsx"
    )
    before_hash = file_hash(changed_file)

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        try:
            async with AsyncSessionLocal() as db:
                run = await ExecutionService(
                    sandbox=FakeSandbox(
                        sandbox_root=tmp_path
                        / "sandboxes",
                        statuses={
                            "node:test": STATUS_FAIL
                        },
                        mutate_sandbox=True,
                    )
                ).execute_change_set(
                    change_set_id=change_set.id,
                    repository_path=repo,
                    db=db,
                )

                assert run.status == "failed"
                assert run.tests_status == STATUS_FAIL

            assert file_hash(changed_file) == before_hash
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_timeout_persisted_and_cleanup_runs(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)
    sandbox = FakeSandbox(
        sandbox_root=tmp_path / "sandboxes",
        statuses={
            "node:test": STATUS_TIMEOUT
        },
    )

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        try:
            async with AsyncSessionLocal() as db:
                run = await ExecutionService(
                    sandbox=sandbox
                ).execute_change_set(
                    change_set_id=change_set.id,
                    repository_path=repo,
                    db=db,
                )

                assert run.status == "timeout"
                assert run.timed_out is True
                assert any(
                    result["status"] == STATUS_TIMEOUT
                    for result in run.results_json
                )

            assert sandbox.cleanup_called is True
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_docker_unavailable_records_error_without_host_fallback(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)
    sandbox = FakeSandbox(
        sandbox_root=tmp_path / "sandboxes",
        raise_on_execute=True,
    )

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        try:
            async with AsyncSessionLocal() as db:
                run = await ExecutionService(
                    sandbox=sandbox
                ).execute_change_set(
                    change_set_id=change_set.id,
                    repository_path=repo,
                    db=db,
                )

                assert run.status == "error"
                assert run.results_json[0]["status"] == STATUS_ERROR
                assert sandbox.executed

            assert sandbox.cleanup_called is True
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_dependency_install_failure_skips_later_checks(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    create_node_execution_fixture_repo(repo)

    async def run_test():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        try:
            async with AsyncSessionLocal() as db:
                run = await ExecutionService(
                    sandbox=FakeSandbox(
                        sandbox_root=tmp_path
                        / "sandboxes",
                        statuses={
                            "npm:install": STATUS_FAIL
                        },
                    )
                ).execute_change_set(
                    change_set_id=change_set.id,
                    repository_path=repo,
                    db=db,
                )

                assert run.status == "failed"
                assert run.tests_status == STATUS_SKIPPED
                assert all(
                    result["status"]
                    in {
                        STATUS_FAIL,
                        STATUS_SKIPPED,
                    }
                    for result in run.results_json
                )
        finally:
            await cleanup_execution_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())
