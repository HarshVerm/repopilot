import configparser
from pathlib import Path


def normalize_repo_token(
    value: str,
) -> str:
    return value.strip().lower()


def parse_origin_owner_repo(
    repository_path: Path,
) -> tuple[str, str] | None:
    git_config_path = (
        repository_path / ".git" / "config"
    )

    if not git_config_path.exists():
        return None

    parser = configparser.ConfigParser()
    parser.read(
        git_config_path
    )

    section = 'remote "origin"'

    if not parser.has_section(section):
        return None

    url = parser.get(
        section,
        "url",
        fallback="",
    )

    if not url:
        return None

    normalized = (
        url.removesuffix(".git")
        .replace("git@github.com:", "https://github.com/")
    )
    parts = normalized.rstrip("/").split("/")

    if len(parts) < 2:
        return None

    return (
        parts[-2],
        parts[-1],
    )


def workspace_matches_repository(
    *,
    repository_path: Path,
    owner: str,
    repo: str,
) -> bool | None:
    origin = parse_origin_owner_repo(
        repository_path
    )

    if origin is None:
        return None

    origin_owner, origin_repo = origin

    return (
        normalize_repo_token(origin_owner)
        == normalize_repo_token(owner)
        and normalize_repo_token(origin_repo)
        == normalize_repo_token(repo)
    )
