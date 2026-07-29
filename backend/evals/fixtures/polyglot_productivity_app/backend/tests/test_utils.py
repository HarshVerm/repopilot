from backend.app.models import Task
from backend.app.utils import count_by_tag


def test_count_by_tag_counts_first_tag():
    tasks = [
        Task(id=1, title="A", tags=["api", "urgent"]),
        Task(id=2, title="B", tags=["api"]),
    ]

    assert count_by_tag(tasks) == {"api": 2}
