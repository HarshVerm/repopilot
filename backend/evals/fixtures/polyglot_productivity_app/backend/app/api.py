from backend.app.models import TASKS, Task
from backend.app.utils import count_by_tag, normalize_title, parse_due_date


def list_tasks(include_completed: bool = False):
    if include_completed:
        return TASKS

    return [task for task in TASKS if not task.completed]


def create_task(payload: dict) -> Task:
    title = normalize_title(payload.get("title", ""))
    due_date = parse_due_date(payload.get("dueDate"))
    tags = payload.get("tags") or []

    task = Task(id=len(TASKS) + 1, title=title, tags=tags)
    task.due_date = due_date
    TASKS.append(task)
    return task


def stats():
    return {"by_tag": count_by_tag(TASKS)}
