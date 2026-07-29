from pathlib import Path

from app.evaluation.dataset import (
    load_evaluation_suite,
    prepare_fixture_workspace,
)


def test_repopilot_eval_v1_has_20_tasks_and_distribution():
    suite = load_evaluation_suite(
        "repopilot-eval-v1"
    )

    assert len(suite.tasks) == 20
    assert suite.difficulty_distribution() == {
        "easy": 7,
        "medium": 8,
        "hard": 5,
    }
    assert len(
        suite.category_distribution()
    ) >= 10


def test_agent_visible_payload_excludes_evaluator_assets():
    suite = load_evaluation_suite(
        "repopilot-eval-v1"
    )
    payload = suite.tasks[
        0
    ].agent_visible_payload()

    assert "hidden_test_path" not in payload
    assert "relevant_files" not in payload
    assert "expected_modified_files" not in payload
    assert "base_commit_sha" not in payload
    assert "issue_title" in payload
    assert "issue_body" in payload


def test_hidden_tests_are_not_copied_into_fixture_workspace(
    tmp_path: Path,
):
    suite = load_evaluation_suite(
        "repopilot-eval-v1"
    )
    task = suite.tasks[0]
    workspace = prepare_fixture_workspace(
        suite=suite,
        task=task,
        destination_root=tmp_path,
        run_id="dry-run-test",
    )

    assert workspace.exists()
    assert not (
        workspace / "backend/tests/test_hidden_eval.py"
    ).exists()
    assert suite.hidden_test_path(
        task
    ).exists()
