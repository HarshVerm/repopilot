from dataclasses import dataclass, field


@dataclass
class Task:
    id: int
    title: str
    completed: bool = False
    tags: list[str] = field(default_factory=list)


TASKS = [
    Task(id=1, title="Write tests", completed=False, tags=["backend"]),
    Task(id=2, title="Fix search", completed=True, tags=["frontend"]),
]
