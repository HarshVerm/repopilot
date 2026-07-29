from dataclasses import dataclass

from app.core.config import settings
from app.services.sandbox.detector import (
    ProjectDetection,
)
from app.services.sandbox.results import (
    BUILD,
    DEPENDENCY_INSTALL,
    LINT,
    TEST,
    TYPECHECK,
    CommandResult,
    ExecutionCommand,
    skipped_result,
)


class CommandPolicyError(ValueError):
    pass


ALLOWED_EXECUTABLES = {
    "npm",
    "pnpm",
    "yarn",
    "python",
    "poetry",
    "pipenv",
}

NODE_CHECK_SCRIPTS = {
    TEST: "test",
    TYPECHECK: "typecheck",
    LINT: "lint",
    BUILD: "build",
}


@dataclass(frozen=True)
class CommandPlan:
    commands: list[ExecutionCommand]
    skipped_results: list[CommandResult]
    metadata: dict


def build_command_plan(
    detection: ProjectDetection,
) -> CommandPlan:
    commands: list[ExecutionCommand] = []
    skipped: list[CommandResult] = []

    if detection.node:
        add_node_commands(
            detection.node.package_manager,
            detection.node.lockfile,
            detection.node.scripts,
            commands,
            skipped,
        )

    if detection.python:
        add_python_commands(
            detection.python.package_manager,
            detection.python.has_tests,
            detection.python.has_requirements,
            commands,
            skipped,
        )

    return CommandPlan(
        commands=commands,
        skipped_results=skipped,
        metadata=detection.to_metadata(),
    )


def add_node_commands(
    package_manager: str,
    lockfile: str | None,
    scripts: dict[str, str],
    commands: list[ExecutionCommand],
    skipped: list[CommandResult],
) -> None:
    commands.append(
        node_install_command(
            package_manager,
            lockfile,
        )
    )

    for command_type, script_name in NODE_CHECK_SCRIPTS.items():
        if script_name in scripts:
            commands.append(
                node_script_command(
                    package_manager,
                    command_type,
                    script_name,
                )
            )
        else:
            skipped.append(
                skipped_result(
                    name=f"node:{script_name}",
                    command_type=command_type,
                    reason=(
                        f"No {script_name} script declared"
                    ),
                )
            )


def node_install_command(
    package_manager: str,
    lockfile: str | None,
) -> ExecutionCommand:
    if package_manager == "pnpm":
        executable = "pnpm"
        args = [
            "install",
            "--frozen-lockfile",
        ]
    elif package_manager == "yarn":
        executable = "yarn"
        args = [
            "install",
            "--frozen-lockfile",
        ]
    elif package_manager == "npm":
        executable = "npm"
        args = (
            [
                "ci",
            ]
            if lockfile == "package-lock.json"
            else [
                "install",
                "--no-package-lock",
            ]
        )
    else:
        raise CommandPolicyError(
            "Unsupported Node package manager"
        )

    return ensure_allowed(
        ExecutionCommand(
            name=f"{package_manager}:install",
            command_type=DEPENDENCY_INSTALL,
            executable=executable,
            args=args,
            timeout_seconds=(
                settings.sandbox_command_timeout_seconds
            ),
            network_enabled=True,
            runtime="node",
        )
    )


def node_script_command(
    package_manager: str,
    command_type: str,
    script_name: str,
) -> ExecutionCommand:
    if script_name not in {
        "test",
        "typecheck",
        "lint",
        "build",
    }:
        raise CommandPolicyError(
            "Unsupported package script"
        )

    if package_manager not in {
        "npm",
        "pnpm",
        "yarn",
    }:
        raise CommandPolicyError(
            "Unsupported package manager"
        )

    return ensure_allowed(
        ExecutionCommand(
            name=f"node:{script_name}",
            command_type=command_type,
            executable=package_manager,
            args=[
                "run",
                script_name,
            ],
            timeout_seconds=(
                settings.sandbox_command_timeout_seconds
            ),
            network_enabled=False,
            runtime="node",
        )
    )


def add_python_commands(
    package_manager: str,
    has_tests: bool,
    has_requirements: bool,
    commands: list[ExecutionCommand],
    skipped: list[CommandResult],
) -> None:
    install = python_install_command(
        package_manager,
        has_requirements,
    )

    if install:
        commands.append(install)

    if has_tests:
        commands.append(
            ensure_allowed(
                ExecutionCommand(
                    name="python:pytest",
                    command_type=TEST,
                    executable="python",
                    args=[
                        "-m",
                        "pytest",
                    ],
                    timeout_seconds=(
                        settings.sandbox_command_timeout_seconds
                    ),
                    network_enabled=False,
                    runtime="python",
                )
            )
        )
    else:
        skipped.append(
            skipped_result(
                name="python:pytest",
                command_type=TEST,
                reason="No Python test directory or pytest.ini found",
            )
        )

    for command_type, name in [
        (TYPECHECK, "python:typecheck"),
        (LINT, "python:lint"),
        (BUILD, "python:build"),
    ]:
        skipped.append(
            skipped_result(
                name=name,
                command_type=command_type,
                reason=(
                    "Python "
                    + command_type
                    + " command not declared by Step 7 policy"
                ),
            )
        )


def python_install_command(
    package_manager: str,
    has_requirements: bool,
) -> ExecutionCommand | None:
    if package_manager == "pip":
        if not has_requirements:
            return None

        return ensure_allowed(
            ExecutionCommand(
                name="python:pip-install",
                command_type=DEPENDENCY_INSTALL,
                executable="python",
                args=[
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    "requirements.txt",
                ],
                timeout_seconds=(
                    settings.sandbox_command_timeout_seconds
                ),
                network_enabled=True,
                runtime="python",
            )
        )

    if package_manager == "poetry":
        return ensure_allowed(
            ExecutionCommand(
                name="python:poetry-install",
                command_type=DEPENDENCY_INSTALL,
                executable="poetry",
                args=[
                    "install",
                    "--no-interaction",
                    "--no-root",
                ],
                timeout_seconds=(
                    settings.sandbox_command_timeout_seconds
                ),
                network_enabled=True,
                runtime="python",
            )
        )

    if package_manager == "pipenv":
        return ensure_allowed(
            ExecutionCommand(
                name="python:pipenv-install",
                command_type=DEPENDENCY_INSTALL,
                executable="pipenv",
                args=[
                    "install",
                    "--dev",
                ],
                timeout_seconds=(
                    settings.sandbox_command_timeout_seconds
                ),
                network_enabled=True,
                runtime="python",
            )
        )

    raise CommandPolicyError(
        "Unsupported Python package manager"
    )


def ensure_allowed(
    command: ExecutionCommand,
) -> ExecutionCommand:
    if command.executable not in ALLOWED_EXECUTABLES:
        raise CommandPolicyError(
            "Executable is not allowed"
        )

    if command.working_directory != ".":
        raise CommandPolicyError(
            "Only repository-root working directory is allowed"
        )

    if any(
        "\x00" in arg
        for arg in command.args
    ):
        raise CommandPolicyError(
            "Command argument contains null byte"
        )

    return command
