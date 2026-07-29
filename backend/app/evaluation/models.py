from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.core.config import settings


EvaluationStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
]

TaskResultStatus = Literal[
    "pending",
    "running",
    "passed",
    "failed",
    "skipped",
    "error",
    "timeout",
]

VerificationStatus = Literal[
    "PASS",
    "FAIL",
    "SKIPPED",
    "TIMEOUT",
    "ERROR",
]


class EvaluationTask(BaseModel):
    id: str = Field(
        min_length=3,
        max_length=100,
    )
    suite_version: str
    title: str = Field(
        min_length=3,
        max_length=200,
    )
    difficulty: Literal[
        "easy",
        "medium",
        "hard",
    ]
    category: str = Field(
        min_length=3,
        max_length=80,
    )
    fixture_path: str
    fixture_hash: str | None = None
    base_commit_sha: str = Field(
        min_length=40,
        max_length=40,
    )
    issue_title: str = Field(
        min_length=1,
        max_length=settings.max_issue_title_chars,
    )
    issue_body: str = Field(
        max_length=settings.max_issue_body_chars,
    )
    relevant_files: list[str]
    expected_modified_files: list[str] | None = None
    protected_files: list[str] = Field(
        default_factory=list
    )
    hidden_test_path: str
    timeout_seconds: int = settings.evaluation_task_timeout_seconds
    tags: list[str] = Field(
        default_factory=list
    )

    @field_validator(
        "fixture_path",
        "hidden_test_path",
    )
    @classmethod
    def validate_relative_paths(
        cls,
        value: str,
    ) -> str:
        path = Path(value)

        if (
            path.is_absolute()
            or ".." in path.parts
            or not value.strip()
        ):
            raise ValueError(
                "evaluation asset paths must be safe relative paths"
            )

        return path.as_posix()

    @field_validator(
        "relevant_files",
        "expected_modified_files",
        "protected_files",
        "tags",
    )
    @classmethod
    def validate_non_empty_strings(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return value

        if any(
            not item.strip()
            for item in value
        ):
            raise ValueError(
                "list values must not be blank"
            )

        return [
            item.strip()
            for item in value
        ]

    def agent_visible_payload(
        self,
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "suite_version": self.suite_version,
            "title": self.title,
            "difficulty": self.difficulty,
            "category": self.category,
            "issue_title": self.issue_title,
            "issue_body": self.issue_body,
            "protected_files": list(
                self.protected_files
            ),
            "timeout_seconds": self.timeout_seconds,
            "tags": list(self.tags),
        }


class EvaluationSuiteDefinition(BaseModel):
    suite_name: str
    suite_version: str
    tasks: list[EvaluationTask]


class VerificationResults(BaseModel):
    tests: VerificationStatus = "SKIPPED"
    lint: VerificationStatus = "SKIPPED"
    typecheck: VerificationStatus = "SKIPPED"
    build: VerificationStatus = "SKIPPED"


class EvaluationTaskResultData(BaseModel):
    evaluation_task_id: str
    status: TaskResultStatus
    difficulty: str
    category: str
    repo_pilot_task_id: str | None = None
    retrieval_recall_at_1: float = 0.0
    retrieval_recall_at_3: float = 0.0
    retrieval_recall_at_5: float = 0.0
    retrieval_recall_at_10: float = 0.0
    retrieval_precision_at_5: float | None = None
    planner_relevant_file_recall: float = 0.0
    planner_hallucinated_files: int = 0
    planner_extra_modify_files: int = 0
    first_patch_passed: bool = False
    debug_attempts: int = 0
    debug_recovered: bool = False
    visible_tests_passed: bool = False
    hidden_tests_passed: bool = False
    final_success: bool = False
    verification: VerificationResults = Field(
        default_factory=VerificationResults
    )
    files_changed: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None
    duration_ms: int = 0
    failure_category: str | None = None
    security_violations_attempted: int = 0
    security_violations_applied: int = 0


class EvaluationRunData(BaseModel):
    run_id: str
    suite_name: str
    suite_version: str
    status: EvaluationStatus
    repopilot_commit_sha: str | None
    configuration: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None = None
    results: list[EvaluationTaskResultData] = Field(
        default_factory=list
    )
