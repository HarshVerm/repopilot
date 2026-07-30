# Module purpose: Implement detector behavior for the sandbox execution domain.

import json
from dataclasses import dataclass
from pathlib import Path


# Purpose: Signal project detection failures.
class ProjectDetectionError(ValueError):
    pass


# Purpose: Encapsulate node project behavior for the sandbox execution domain.
@dataclass(frozen=True)
class NodeProject:
    package_manager: str
    lockfile: str | None
    scripts: dict[str, str]


# Purpose: Encapsulate python project behavior for the sandbox execution domain.
@dataclass(frozen=True)
class PythonProject:
    package_manager: str
    has_tests: bool
    has_requirements: bool


# Purpose: Encapsulate project detection behavior for the sandbox execution domain.
@dataclass(frozen=True)
class ProjectDetection:
    node: NodeProject | None
    python: PythonProject | None

    # Purpose: Handle project types for the sandbox execution workflow.
    @property
    def project_types(self) -> list[str]:
        types: list[str] = []

        if self.node:
            types.append("node")

        if self.python:
            types.append("python")

        return types

    # Purpose: Handle to metadata for the sandbox execution workflow.
    def to_metadata(self) -> dict:
        return {
            "project_types": self.project_types,
            "node_package_manager": (
                self.node.package_manager
                if self.node
                else None
            ),
            "node_lockfile": (
                self.node.lockfile
                if self.node
                else None
            ),
            "python_package_manager": (
                self.python.package_manager
                if self.python
                else None
            ),
        }


# Purpose: Detect project for the sandbox execution workflow.
def detect_project(
    repository_path: Path,
) -> ProjectDetection:
    return ProjectDetection(
        node=detect_node_project(
            repository_path
        ),
        python=detect_python_project(
            repository_path
        ),
    )


# Purpose: Detect node project for the sandbox execution workflow.
def detect_node_project(
    repository_path: Path,
) -> NodeProject | None:
    package_json = (
        repository_path / "package.json"
    )

    if not package_json.is_file():
        return None

    try:
        data = json.loads(
            package_json.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise ProjectDetectionError(
            "package.json is not valid JSON"
        ) from exc

    scripts = data.get(
        "scripts",
        {},
    )

    if not isinstance(
        scripts,
        dict,
    ):
        scripts = {}

    lockfiles = [
        name
        for name in [
            "pnpm-lock.yaml",
            "yarn.lock",
            "package-lock.json",
        ]
        if (repository_path / name).is_file()
    ]

    if len(lockfiles) > 1:
        raise ProjectDetectionError(
            "Conflicting Node lockfiles: "
            + ", ".join(lockfiles)
        )

    package_manager = "npm"

    if lockfiles:
        package_manager = {
            "pnpm-lock.yaml": "pnpm",
            "yarn.lock": "yarn",
            "package-lock.json": "npm",
        }[lockfiles[0]]

    return NodeProject(
        package_manager=package_manager,
        lockfile=(
            lockfiles[0]
            if lockfiles
            else None
        ),
        scripts={
            str(key): str(value)
            for key, value in scripts.items()
            if isinstance(key, str)
            and isinstance(value, str)
        },
    )


# Purpose: Detect python project for the sandbox execution workflow.
def detect_python_project(
    repository_path: Path,
) -> PythonProject | None:
    pyproject = repository_path / "pyproject.toml"
    requirements = repository_path / "requirements.txt"
    pipfile = repository_path / "Pipfile"
    setup_py = repository_path / "setup.py"
    setup_cfg = repository_path / "setup.cfg"

    if (
        not pyproject.is_file()
        and not requirements.is_file()
        and not pipfile.is_file()
        and not setup_py.is_file()
        and not setup_cfg.is_file()
    ):
        return None

    package_manager = "pip"

    if pipfile.is_file():
        package_manager = "pipenv"
    elif (repository_path / "poetry.lock").is_file():
        package_manager = "poetry"
    elif pyproject.is_file():
        text = pyproject.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        if "[tool.poetry]" in text:
            package_manager = "poetry"

    has_tests = any(
        path.is_file() or path.is_dir()
        for path in [
            repository_path / "tests",
            repository_path / "test",
            repository_path / "pytest.ini",
        ]
    )

    return PythonProject(
        package_manager=package_manager,
        has_tests=has_tests,
        has_requirements=requirements.is_file(),
    )
