from app.schemas.github import (
    IssueResponse,
    RepositoryResponse,
)


def map_repository(data: dict) -> RepositoryResponse:
    return RepositoryResponse(
        id=data["id"],
        name=data["name"],
        full_name=data["full_name"],
        description=data.get("description"),
        private=data["private"],
        default_branch=data["default_branch"],
        clone_url=data["clone_url"],
        language=data.get("language"),
        stars=data["stargazers_count"],
    )


def map_issue(data: dict) -> IssueResponse:
    return IssueResponse(
        id=data["id"],
        number=data["number"],
        title=data["title"],
        body=data.get("body"),
        state=data["state"],
        html_url=data["html_url"],
        comments=data["comments"],
        labels=[
            label["name"]
            for label in data.get("labels", [])
        ],
    )