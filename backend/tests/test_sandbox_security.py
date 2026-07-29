import os
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.sandbox.docker import (
    DockerSandbox,
    SandboxHandle,
)
from app.services.sandbox.filesystem import (
    SandboxFilesystemError,
    cleanup_sandbox,
    create_sandbox_copy,
)
from app.services.sandbox.policy import (
    safe_container_environment,
)
from app.services.sandbox.results import (
    STATUS_TIMEOUT,
    TEST,
    ExecutionCommand,
    truncate_bytes,
)
from tests.coding_fixtures import (
    write_file,
)


def test_sandbox_copy_preserves_symlink_without_copying_target(
    tmp_path: Path,
):
    source = tmp_path / "source"
    source.mkdir()
    external = tmp_path / "external-secret.txt"
    external.write_text(
        "secret\n",
        encoding="utf-8",
    )
    write_file(
        source,
        "src/index.ts",
        "export const ok = true;\n",
    )
    write_file(
        source,
        ".env",
        "SECRET=true\n",
    )
    (source / ".git").mkdir()
    (source / "external-link").symlink_to(
        external
    )
    sandbox_root = tmp_path / "sandboxes"

    sandbox_repo = create_sandbox_copy(
        execution_run_id=uuid.uuid4(),
        source_repository=source,
        sandbox_root=sandbox_root,
    )

    assert (
        sandbox_repo / "external-link"
    ).is_symlink()
    assert not (
        sandbox_repo / ".env"
    ).exists()
    assert not (
        sandbox_repo / ".git"
    ).exists()
    assert (
        sandbox_repo / "external-link"
    ).resolve() == external


def test_cleanup_refuses_paths_outside_sandbox_root(
    tmp_path: Path,
):
    outside = tmp_path / "outside"
    outside.mkdir()
    sandbox_root = tmp_path / "sandboxes"
    sandbox_root.mkdir()

    with pytest.raises(
        SandboxFilesystemError
    ):
        cleanup_sandbox(
            outside,
            sandbox_root=sandbox_root,
        )

    assert outside.exists()


def test_docker_args_apply_security_and_resource_policy(
    tmp_path: Path,
):
    sandbox = DockerSandbox(
        sandbox_root=tmp_path / "sandboxes"
    )
    repository = tmp_path / "repo"
    repository.mkdir()
    handle = SandboxHandle(
        execution_run_id=uuid.uuid4(),
        run_directory=tmp_path / "run",
        repository_path=repository,
    )
    command = ExecutionCommand(
        name="node:test",
        command_type=TEST,
        executable="npm",
        args=[
            "run",
            "test",
        ],
        network_enabled=False,
        runtime="node",
    )

    args = sandbox.build_docker_run_args(
        handle=handle,
        command=command,
        container_name="repopilot-run-test",
    )
    joined = " ".join(args)

    assert "--privileged" not in args
    assert "/var/run/docker.sock" not in joined
    assert "--network" in args
    assert "none" in args
    assert "--cpus" in args
    assert "--memory" in args
    assert "--pids-limit" in args
    assert "--mount" in args
    assert str(repository) in joined
    assert "/workspace" in joined
    assert "npm" in args
    assert "test" in args


def test_container_environment_does_not_include_host_secret(
    monkeypatch,
):
    monkeypatch.setenv(
        "REPOPILOT_TEST_SECRET",
        "do-not-expose",
    )

    env = safe_container_environment()

    assert env == {
        "CI": "true",
        "REPOPILOT_SANDBOX": "true",
    }
    assert os.environ["REPOPILOT_TEST_SECRET"] == "do-not-expose"


def test_docker_timeout_removes_container(
    monkeypatch,
    tmp_path: Path,
):
    calls: list[list[str]] = []

    def fake_run(
        args,
        **kwargs,
    ):
        calls.append(args)

        if args[:2] == [
            "docker",
            "run",
        ]:
            raise subprocess.TimeoutExpired(
                cmd=args,
                timeout=1,
                output=b"partial",
                stderr=b"slow",
            )

        return SimpleNamespace(
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    monkeypatch.setattr(
        "app.services.sandbox.docker.subprocess.run",
        fake_run,
    )
    sandbox = DockerSandbox(
        sandbox_root=tmp_path / "sandboxes"
    )
    repository = tmp_path / "repo"
    repository.mkdir()
    handle = SandboxHandle(
        execution_run_id=uuid.uuid4(),
        run_directory=tmp_path / "run",
        repository_path=repository,
    )
    command = ExecutionCommand(
        name="node:test",
        command_type=TEST,
        executable="npm",
        args=[
            "run",
            "test",
        ],
        timeout_seconds=1,
    )

    result = sandbox.execute(
        handle=handle,
        command=command,
    )

    assert result.status == STATUS_TIMEOUT
    assert any(
        call[:3]
        == [
            "docker",
            "rm",
            "-f",
        ]
        for call in calls
    )


def test_output_truncation_keeps_bounded_tail():
    text, truncated = truncate_bytes(
        b"abcdefghij",
        limit=4,
    )

    assert text == "ghij"
    assert truncated is True
