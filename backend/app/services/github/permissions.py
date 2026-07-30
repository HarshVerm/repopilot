# Module purpose: Implement permissions behavior for the GitHub integration domain.

from collections.abc import Mapping


REQUIRED_PUBLICATION_PERMISSIONS = {
    "contents": "write",
    "pull_requests": "write",
}


# Purpose: Normalize app permissions for the GitHub integration workflow.
def normalize_app_permissions(
    permissions: Mapping | None,
) -> dict[str, str]:
    return {
        str(name): str(level).casefold()
        for name, level in (permissions or {}).items()
        if name is not None and level is not None
    }


# Purpose: Handle missing publication permissions for the GitHub integration workflow.
def missing_publication_permissions(
    permissions: Mapping | None,
) -> list[str]:
    normalized = normalize_app_permissions(
        permissions
    )
    return [
        name
        for name, required_level
        in REQUIRED_PUBLICATION_PERMISSIONS.items()
        if normalized.get(name) != required_level
    ]


# Purpose: Handle repository capabilities from app permissions for the GitHub integration workflow.
def repository_capabilities_from_app_permissions(
    permissions: Mapping | None,
) -> dict[str, bool]:
    normalized = normalize_app_permissions(
        permissions
    )
    contents = normalized.get("contents")
    pull_requests = normalized.get(
        "pull_requests"
    )
    issues = normalized.get("issues")

    return {
        "pull": contents in {"read", "write"},
        "push": contents == "write",
        "pull_requests": pull_requests == "write",
        "issues": issues == "write",
    }
