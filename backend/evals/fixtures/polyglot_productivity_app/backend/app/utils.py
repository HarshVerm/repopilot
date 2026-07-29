from collections import defaultdict
from datetime import date


def normalize_title(title: str) -> str:
    return title.strip().title()


def parse_due_date(value: str | None) -> date | None:
    if not value:
        return None

    month, day, year = value.split("/")
    return date(int(year), int(month), int(day))


def count_by_tag(tasks) -> dict[str, int]:
    counts = defaultdict(int)

    for task in tasks:
        if task.tags:
            counts[task.tags[0]] += 1

    return dict(counts)


async def enrich_task(task, loader):
    details = loader(task.id)
    return {**task.__dict__, "details": details}
