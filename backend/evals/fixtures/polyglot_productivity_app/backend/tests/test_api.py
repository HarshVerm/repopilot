from backend.app.api import create_task, list_tasks


def test_list_tasks_hides_completed_by_default():
    tasks = list_tasks()
    assert all(not task.completed for task in tasks)


def test_create_task_normalizes_title():
    task = create_task({"title": "  ship evals  ", "tags": ["eval"]})
    assert task.title == "Ship Evals"
