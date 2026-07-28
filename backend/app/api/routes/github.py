from fastapi import APIRouter, HTTPException
import httpx

from app.schemas.github import (
    IssueResponse,
    RepositoryResponse,
)
from app.services.github.client import github_client
from app.schemas.mapper import (
    map_issue,
    map_repository,
)

router = APIRouter(
    prefix="/github",
    tags=["github"],
)


@router.get(
    "/repos/{owner}/{repo}",
    response_model=RepositoryResponse,
)
async def get_repository(
    owner: str,
    repo: str,
):
    try:
        data = await github_client.get_repository(
            owner,
            repo,
        )

        return map_repository(data)

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Repository not found",
            )

        raise


@router.get(
    "/repos/{owner}/{repo}/issues",
    response_model=list[IssueResponse],
)
async def list_repository_issues(
    owner: str,
    repo: str,
    state: str = "open",
):
    data = await github_client.list_issues(
        owner=owner,
        repo=repo,
        state=state,
    )

    return [
        map_issue(issue)
        for issue in data
    ]


@router.get(
    "/repos/{owner}/{repo}/issues/{issue_number}",
    response_model=IssueResponse,
)
async def get_repository_issue(
    owner: str,
    repo: str,
    issue_number: int,
):
    try:
        data = await github_client.get_issue(
            owner,
            repo,
            issue_number,
        )

        return map_issue(data)

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Issue not found",
            )

        raise
