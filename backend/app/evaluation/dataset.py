# Module purpose: Implement dataset behavior for the evaluation domain.

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.evaluation.models import (
    EvaluationSuiteDefinition,
    EvaluationTask,
)


EVALS_ROOT = Path(__file__).resolve().parents[2] / "evals"
TASKS_ROOT = EVALS_ROOT / "tasks"
FIXTURES_ROOT = EVALS_ROOT / "fixtures"
HIDDEN_TESTS_ROOT = EVALS_ROOT / "hidden_tests"
REPORTS_ROOT = EVALS_ROOT / "reports"


# Purpose: Signal evaluation dataset failures.
class EvaluationDatasetError(ValueError):
    pass


# Purpose: Encapsulate evaluation suite behavior for the evaluation domain.
@dataclass(frozen=True)
class EvaluationSuite:
    suite_name: str
    suite_version: str
    tasks: tuple[EvaluationTask, ...]
    root: Path = EVALS_ROOT

    # Purpose: Handle filtered for the evaluation workflow.
    def filtered(
        self,
        *,
        task_id: str | None = None,
        difficulty: str | None = None,
        category: str | None = None,
        max_tasks: int | None = None,
    ) -> "EvaluationSuite":
        tasks = list(self.tasks)

        if task_id:
            tasks = [
                task
                for task in tasks
                if task.id == task_id
            ]
        if difficulty:
            tasks = [
                task
                for task in tasks
                if task.difficulty == difficulty
            ]
        if category:
            tasks = [
                task
                for task in tasks
                if task.category == category
            ]
        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        return EvaluationSuite(
            suite_name=self.suite_name,
            suite_version=self.suite_version,
            tasks=tuple(tasks),
            root=self.root,
        )

    # Purpose: Validate evaluation for the evaluation workflow.
    def validate(
        self,
        *,
        require_minimum_tasks: bool = True,
    ) -> None:
        if require_minimum_tasks and len(self.tasks) < 20:
            raise EvaluationDatasetError(
                "evaluation suite must contain at least 20 tasks"
            )

        seen_ids: set[str] = set()
        base_sha_by_fixture: dict[str, str] = {}

        for task in self.tasks:
            if task.id in seen_ids:
                raise EvaluationDatasetError(
                    f"duplicate evaluation task id: {task.id}"
                )

            seen_ids.add(task.id)

            if task.suite_version != self.suite_version:
                raise EvaluationDatasetError(
                    f"{task.id} suite version mismatch"
                )

            fixture_path = self.fixture_path(
                task
            )
            hidden_path = self.hidden_test_path(
                task
            )

            if not fixture_path.exists():
                raise EvaluationDatasetError(
                    f"{task.id} fixture path does not exist"
                )

            if not hidden_path.exists():
                raise EvaluationDatasetError(
                    f"{task.id} hidden test path does not exist"
                )

            if is_relative_to(
                hidden_path.resolve(),
                fixture_path.resolve(),
            ):
                raise EvaluationDatasetError(
                    f"{task.id} hidden tests are inside agent-visible fixture"
                )

            if task.fixture_hash:
                actual_hash = fixture_content_hash(
                    fixture_path
                )

                if actual_hash != task.fixture_hash:
                    raise EvaluationDatasetError(
                        f"{task.id} fixture hash mismatch"
                    )

            fixture_key = fixture_path.resolve().as_posix()
            if fixture_key not in base_sha_by_fixture:
                base_sha_by_fixture[fixture_key] = (
                    deterministic_fixture_base_sha(
                        fixture_path
                    )
                )

            if base_sha_by_fixture[fixture_key] != task.base_commit_sha:
                raise EvaluationDatasetError(
                    f"{task.id} base commit SHA mismatch"
                )

            validate_hidden_asset(
                hidden_path
            )

    # Purpose: Handle fixture path for the evaluation workflow.
    def fixture_path(
        self,
        task: EvaluationTask,
    ) -> Path:
        return self.root / task.fixture_path

    # Purpose: Handle hidden test path for the evaluation workflow.
    def hidden_test_path(
        self,
        task: EvaluationTask,
    ) -> Path:
        return self.root / task.hidden_test_path

    # Purpose: Handle difficulty distribution for the evaluation workflow.
    def difficulty_distribution(
        self,
    ) -> dict[str, int]:
        return distribution(
            task.difficulty
            for task in self.tasks
        )

    # Purpose: Handle category distribution for the evaluation workflow.
    def category_distribution(
        self,
    ) -> dict[str, int]:
        return distribution(
            task.category
            for task in self.tasks
        )


# Purpose: Load evaluation suite for the evaluation workflow.
def load_evaluation_suite(
    suite_version: str = settings.evaluation_suite_version,
    *,
    root: Path = EVALS_ROOT,
) -> EvaluationSuite:
    suite_path = (
        root
        / "tasks"
        / suite_version
        / "tasks.json"
    )

    with suite_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        definition = EvaluationSuiteDefinition.model_validate_json(
            file.read()
        )

    suite = EvaluationSuite(
        suite_name=definition.suite_name,
        suite_version=definition.suite_version,
        tasks=tuple(definition.tasks),
        root=root,
    )
    suite.validate()
    return suite


# Purpose: Handle fixture content hash for the evaluation workflow.
def fixture_content_hash(
    fixture_path: Path,
) -> str:
    digest = hashlib.sha256()

    for path in sorted(
        fixture_path.rglob("*")
    ):
        if path.is_dir():
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue

        relative = path.relative_to(
            fixture_path
        ).as_posix()
        digest.update(
            relative.encode("utf-8")
        )
        digest.update(b"\0")
        digest.update(
            path.read_bytes()
        )
        digest.update(b"\0")

    return digest.hexdigest()


# Purpose: Prepare fixture workspace for the evaluation workflow.
def prepare_fixture_workspace(
    *,
    suite: EvaluationSuite,
    task: EvaluationTask,
    destination_root: Path = settings.evaluation_workspaces_root,
    run_id: str,
) -> Path:
    source = suite.fixture_path(
        task
    )
    workspace_path = (
        destination_root
        / run_id
        / task.id
        / "repository"
    )
    resolved_root = destination_root.resolve()
    resolved_workspace = workspace_path.resolve()

    if not is_relative_to(
        resolved_workspace,
        resolved_root,
    ):
        raise EvaluationDatasetError(
            "evaluation workspace escapes configured root"
        )

    if workspace_path.exists():
        shutil.rmtree(
            workspace_path.parent
        )

    workspace_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copytree(
        source,
        workspace_path,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
        ),
    )
    initialize_fixture_git_repo(
        workspace_path
    )
    head_sha = git_head(
        workspace_path
    )

    if head_sha != task.base_commit_sha:
        raise EvaluationDatasetError(
            f"{task.id} base SHA mismatch: {head_sha}"
        )

    return workspace_path


# Purpose: Handle deterministic fixture base sha for the evaluation workflow.
def deterministic_fixture_base_sha(
    fixture_path: Path,
) -> str:
    import tempfile

    with tempfile.TemporaryDirectory(
        prefix="repopilot-fixture-sha-"
    ) as root:
        repo = Path(root) / "repository"
        shutil.copytree(
            fixture_path,
            repo,
            symlinks=True,
            ignore=shutil.ignore_patterns(
                ".git",
                "__pycache__",
            ),
        )
        initialize_fixture_git_repo(
            repo
        )
        return git_head(
            repo
        )


# Purpose: Handle initialize fixture git repo for the evaluation workflow.
def initialize_fixture_git_repo(
    repository_path: Path,
) -> None:
    run_git(
        repository_path,
        [
            "init",
            str(repository_path),
        ],
        before_init=True,
    )
    run_git(
        repository_path,
        [
            "checkout",
            "-b",
            "main",
        ],
    )
    run_git(
        repository_path,
        [
            "add",
            ".",
        ],
    )
    run_git(
        repository_path,
        [
            "-c",
            "user.name=RepoPilot Eval",
            "-c",
            "user.email=evaluation@example.com",
            "commit",
            "-m",
            "Initial evaluation fixture",
        ],
        env={
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        },
    )


# Purpose: Run git for the evaluation workflow.
def run_git(
    repository_path: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    before_init: bool = False,
) -> str:
    command = [
        "git",
    ]

    if not before_init:
        command.extend(
            [
                "-C",
                str(repository_path),
            ]
        )

    command.extend(args)
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        env={
            **os.environ,
            **(env or {}),
        },
    )

    if result.returncode != 0:
        raise EvaluationDatasetError(
            result.stderr.strip()
            or result.stdout.strip()
        )

    return result.stdout


# Purpose: Handle git head for the evaluation workflow.
def git_head(
    repository_path: Path,
) -> str:
    return run_git(
        repository_path,
        [
            "rev-parse",
            "HEAD",
        ],
    ).strip()


# Purpose: Validate hidden asset for the evaluation workflow.
def validate_hidden_asset(
    hidden_path: Path,
) -> None:
    with hidden_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(
        data.get("files"),
        list,
    ) or not isinstance(
        data.get("commands"),
        list,
    ):
        raise EvaluationDatasetError(
            f"hidden test manifest is invalid: {hidden_path}"
        )


# Purpose: Handle distribution for the evaluation workflow.
def distribution(
    values,
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for value in values:
        counts[value] = counts.get(
            value,
            0,
        ) + 1

    return counts


# Purpose: Return whether relative to.
def is_relative_to(
    path: Path,
    parent: Path,
) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False

    return True
