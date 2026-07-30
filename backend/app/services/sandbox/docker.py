# Module purpose: Implement docker behavior for the sandbox execution domain.

import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.services.sandbox.filesystem import (
    cleanup_sandbox,
    create_sandbox_copy,
)
from app.services.sandbox.policy import (
    safe_container_environment,
)
from app.services.sandbox.results import (
    STATUS_ERROR,
    CommandResult,
    ExecutionCommand,
    command_result_from_exit,
    timeout_result,
    truncate_bytes,
)


# Purpose: Signal sandbox preparation failures.
class SandboxPreparationError(RuntimeError):
    pass


# Purpose: Signal sandbox execution failures.
class SandboxExecutionError(RuntimeError):
    pass


# Purpose: Signal sandbox cleanup failures.
class SandboxCleanupError(RuntimeError):
    pass


# Purpose: Encapsulate sandbox handle behavior for the sandbox execution domain.
@dataclass
class SandboxHandle:
    execution_run_id: uuid.UUID
    run_directory: Path
    repository_path: Path
    container_names: list[str] = field(
        default_factory=list
    )


# Purpose: Encapsulate docker sandbox behavior for the sandbox execution domain.
class DockerSandbox:
    runtime_name = "docker"

    # Purpose: Initialize docker sandbox state and dependencies.
    def __init__(
        self,
        *,
        sandbox_root: Path = settings.sandbox_root,
    ) -> None:
        self.sandbox_root = sandbox_root

    # Purpose: Prepare sandbox execution for the sandbox execution workflow.
    def prepare(
        self,
        *,
        execution_run_id: uuid.UUID,
        source_repository: Path,
    ) -> SandboxHandle:
        try:
            repository_path = create_sandbox_copy(
                execution_run_id=execution_run_id,
                source_repository=source_repository,
                sandbox_root=self.sandbox_root,
            )
        except Exception as exc:
            raise SandboxPreparationError(
                "Unable to prepare sandbox copy"
            ) from exc

        return SandboxHandle(
            execution_run_id=execution_run_id,
            run_directory=repository_path.parent,
            repository_path=repository_path,
        )

    # Purpose: Execute sandbox execution for the sandbox execution workflow.
    def execute(
        self,
        *,
        handle: SandboxHandle,
        command: ExecutionCommand,
    ) -> CommandResult:
        container_name = (
            "repopilot-run-"
            + handle.execution_run_id.hex[:12]
            + "-"
            + str(
                len(handle.container_names) + 1
            )
        )
        handle.container_names.append(
            container_name
        )
        args = self.build_docker_run_args(
            handle=handle,
            command=command,
            container_name=container_name,
        )
        started_at = time.perf_counter()

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                check=False,
                timeout=command.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            self.remove_container(
                container_name
            )
            return timeout_result(
                command=command,
                duration_ms=(
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                stdout=exc.stdout,
                stderr=exc.stderr,
            )
        except FileNotFoundError as exc:
            raise SandboxExecutionError(
                "Docker executable is not available"
            ) from exc
        finally:
            self.remove_container(
                container_name
            )

        duration_ms = (
            time.perf_counter() - started_at
        ) * 1000

        if result.returncode == 125:
            stdout, stdout_truncated = truncate_bytes(
                result.stdout,
                limit=settings.sandbox_stdout_max_bytes,
            )
            stderr, stderr_truncated = truncate_bytes(
                result.stderr,
                limit=settings.sandbox_stderr_max_bytes,
            )

            return CommandResult(
                name=command.name,
                command_type=command.command_type,
                status=STATUS_ERROR,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                stdout=stdout,
                stderr=stderr,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
            )

        return command_result_from_exit(
            command=command,
            exit_code=result.returncode,
            duration_ms=duration_ms,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    # Purpose: Clean up sandbox execution for the sandbox execution workflow.
    def cleanup(
        self,
        handle: SandboxHandle | None,
    ) -> list[str]:
        errors: list[str] = []

        if handle is None:
            return errors

        for container_name in handle.container_names:
            try:
                self.remove_container(
                    container_name
                )
            except Exception as exc:
                errors.append(
                    "container cleanup failed: "
                    + exc.__class__.__name__
                )

        try:
            cleanup_sandbox(
                handle.run_directory,
                sandbox_root=self.sandbox_root,
            )
        except FileNotFoundError:
            pass
        except Exception as exc:
            errors.append(
                "sandbox cleanup failed: "
                + exc.__class__.__name__
            )

        return errors

    # Purpose: Build docker run args for the sandbox execution workflow.
    def build_docker_run_args(
        self,
        *,
        handle: SandboxHandle,
        command: ExecutionCommand,
        container_name: str,
    ) -> list[str]:
        network = self.network_for_command(
            command
        )
        image = self.image_for_command(
            command
        )
        args = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--cpus",
            str(settings.sandbox_cpu_limit),
            "--memory",
            str(settings.sandbox_memory_limit),
            "--pids-limit",
            str(settings.sandbox_pids_limit),
            "--network",
            network,
            "--workdir",
            "/workspace",
            "--mount",
            "type=bind,source="
            + str(handle.repository_path)
            + ",target=/workspace",
        ]

        if settings.sandbox_container_user:
            args.extend(
                [
                    "--user",
                    settings.sandbox_container_user,
                ]
            )

        for key, value in safe_container_environment().items():
            args.extend(
                [
                    "-e",
                    f"{key}={value}",
                ]
            )

        args.extend(
            [
                image,
                command.executable,
                *command.args,
            ]
        )

        return args

    # Purpose: Handle image for command for the sandbox execution workflow.
    def image_for_command(
        self,
        command: ExecutionCommand,
    ) -> str:
        if command.runtime == "python":
            return settings.sandbox_python_image

        return settings.sandbox_node_image

    # Purpose: Handle network for command for the sandbox execution workflow.
    def network_for_command(
        self,
        command: ExecutionCommand,
    ) -> str:
        network = (
            settings.sandbox_install_network
            if command.network_enabled
            else settings.sandbox_execution_network
        )

        if network == "host" or network.startswith(
            "container:"
        ):
            raise SandboxPreparationError(
                "Unsafe Docker network mode"
            )

        return network

    # Purpose: Remove container for the sandbox execution workflow.
    def remove_container(
        self,
        container_name: str,
    ) -> None:
        subprocess.run(
            [
                "docker",
                "rm",
                "-f",
                container_name,
            ],
            capture_output=True,
            check=False,
        )
