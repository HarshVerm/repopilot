from app.core.config import settings


class PlannerInputError(ValueError):
    pass


def normalize_issue_body(
    issue: dict,
) -> str:
    body = issue.get("body")

    if not body:
        return ""

    return str(body)


def build_planner_input(
    *,
    owner: str,
    repo: str,
    issue: dict,
    context_pack: dict,
) -> str:
    estimated_tokens = int(
        context_pack.get(
            "estimated_tokens",
            0,
        )
        or 0
    )

    if estimated_tokens > settings.max_context_tokens:
        raise PlannerInputError(
            "Context Pack exceeds configured token budget"
        )

    sections = [
        "Repository:",
        f"{owner}/{repo}",
        "",
        "GitHub Issue:",
        f"Number: {issue.get('number')}",
        f"Title: {issue.get('title', '')}",
        "Body:",
        normalize_issue_body(issue),
        "",
        "Retrieved Context Pack:",
        f"Query: {context_pack.get('query', '')}",
        f"Estimated Tokens: {estimated_tokens}",
        "",
    ]

    for file_entry in context_pack.get(
        "files",
        [],
    ):
        file_path = file_entry.get(
            "path",
            ""
        )
        sections.extend(
            [
                f"File: {file_path}",
                "",
            ]
        )

        for chunk in file_entry.get(
            "chunks",
            [],
        ):
            sections.extend(
                [
                    f"Symbol: {chunk.get('symbol')}",
                    f"Kind: {chunk.get('kind')}",
                    (
                        "Lines: "
                        f"{chunk.get('start_line')}-"
                        f"{chunk.get('end_line')}"
                    ),
                    (
                        "Matched By: "
                        + ", ".join(
                            chunk.get(
                                "matched_by",
                                [],
                            )
                        )
                    ),
                    "Source:",
                    chunk.get(
                        "content",
                        "",
                    ),
                    "",
                ]
            )

    return "\n".join(sections)
