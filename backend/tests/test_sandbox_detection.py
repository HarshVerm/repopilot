from pathlib import Path

import pytest

from app.services.sandbox.commands import (
    build_command_plan,
)
from app.services.sandbox.detector import (
    ProjectDetectionError,
    detect_project,
)
from app.services.sandbox.results import (
    BUILD,
    LINT,
    STATUS_SKIPPED,
    TEST,
    TYPECHECK,
)
from tests.coding_fixtures import (
    write_file,
)
from tests.execution_fixtures import (
    package_json,
)


def test_detects_node_npm_and_declared_scripts(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "package.json",
        package_json(
            {
                "test": "vitest run",
                "build": "tsc",
            }
        ),
    )
    write_file(
        repo,
        "package-lock.json",
        "{}\n",
    )

    detection = detect_project(repo)

    assert detection.node
    assert detection.node.package_manager == "npm"
    assert detection.node.scripts["test"] == "vitest run"

    plan = build_command_plan(detection)
    command_names = [
        command.name
        for command in plan.commands
    ]
    skipped_types = {
        result.command_type
        for result in plan.skipped_results
        if result.status == STATUS_SKIPPED
    }

    assert "npm:install" in command_names
    assert "node:test" in command_names
    assert "node:build" in command_names
    assert TYPECHECK in skipped_types
    assert LINT in skipped_types
    npm_install = next(
        command
        for command in plan.commands
        if command.name == "npm:install"
    )
    assert npm_install.args == [
        "ci"
    ]


@pytest.mark.parametrize(
    ("lockfile", "manager"),
    [
        (
            "pnpm-lock.yaml",
            "pnpm",
        ),
        (
            "yarn.lock",
            "yarn",
        ),
    ],
)
def test_detects_node_package_managers(
    tmp_path: Path,
    lockfile: str,
    manager: str,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "package.json",
        package_json(
            {
                "test": "vitest run"
            }
        ),
    )
    write_file(
        repo,
        lockfile,
        "\n",
    )

    detection = detect_project(repo)

    assert detection.node
    assert detection.node.package_manager == manager


def test_conflicting_node_lockfiles_are_rejected(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "package.json",
        package_json({}),
    )
    write_file(
        repo,
        "package-lock.json",
        "{}\n",
    )
    write_file(
        repo,
        "pnpm-lock.yaml",
        "\n",
    )

    with pytest.raises(
        ProjectDetectionError
    ):
        detect_project(repo)


def test_detects_python_requirements_project(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "requirements.txt",
        "pytest\n",
    )
    (repo / "tests").mkdir()

    detection = detect_project(repo)

    assert detection.python
    assert detection.python.package_manager == "pip"
    assert detection.python.has_requirements is True

    plan = build_command_plan(detection)

    assert [
        command.name
        for command in plan.commands
    ] == [
        "python:pip-install",
        "python:pytest",
    ]


@pytest.mark.parametrize(
    ("filename", "content", "manager"),
    [
        (
            "pyproject.toml",
            "[tool.poetry]\nname = 'demo'\n",
            "poetry",
        ),
        (
            "Pipfile",
            "[packages]\n",
            "pipenv",
        ),
    ],
)
def test_detects_python_dependency_managers(
    tmp_path: Path,
    filename: str,
    content: str,
    manager: str,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        filename,
        content,
    )

    detection = detect_project(repo)

    assert detection.python
    assert detection.python.package_manager == manager


def test_missing_scripts_are_skipped_not_passed(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "package.json",
        package_json(
            {
                "build": "tsc"
            }
        ),
    )

    plan = build_command_plan(
        detect_project(repo)
    )
    skipped = {
        result.command_type: result.status
        for result in plan.skipped_results
    }

    assert skipped[TEST] == STATUS_SKIPPED
    assert skipped[TYPECHECK] == STATUS_SKIPPED
    assert skipped[LINT] == STATUS_SKIPPED
    assert BUILD not in skipped


def test_commands_are_argument_lists_not_shell_strings(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "package.json",
        package_json(
            {
                "test": "echo unsafe; rm -rf /"
            }
        ),
    )

    plan = build_command_plan(
        detect_project(repo)
    )
    test_command = next(
        command
        for command in plan.commands
        if command.command_type == TEST
    )

    assert test_command.executable == "npm"
    assert test_command.args == [
        "run",
        "test",
    ]
