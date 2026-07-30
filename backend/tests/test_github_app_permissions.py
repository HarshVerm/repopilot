from app.services.github.permissions import (
    missing_publication_permissions,
    repository_capabilities_from_app_permissions,
)


def test_publication_uses_github_app_permission_grants():
    permissions = {
        "contents": "write",
        "issues": "read",
        "metadata": "read",
        "pull_requests": "write",
    }

    assert missing_publication_permissions(
        permissions
    ) == []
    assert (
        repository_capabilities_from_app_permissions(
            permissions
        )
        == {
            "pull": True,
            "push": True,
            "pull_requests": True,
            "issues": False,
        }
    )


def test_issue_creation_requires_issue_write_grant():
    permissions = {
        "contents": "write",
        "issues": "write",
        "pull_requests": "write",
    }

    assert (
        repository_capabilities_from_app_permissions(
            permissions
        )["issues"]
        is True
    )


def test_publication_reports_missing_write_grants():
    permissions = {
        "contents": "read",
        "pull_requests": "read",
    }

    assert missing_publication_permissions(
        permissions
    ) == [
        "contents",
        "pull_requests",
    ]
