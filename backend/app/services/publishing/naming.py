import re


class BranchNameError(ValueError):
    pass


MAX_BRANCH_LENGTH = 96


def generate_branch_name(
    *,
    issue_number: int,
    summary: str,
    diff_hash: str,
) -> str:
    slug = slugify(
        summary
    )
    suffix = diff_hash[:7]
    branch = (
        f"repopilot/{issue_number}-{slug}-{suffix}"
    )

    return trim_branch_name(
        branch
    )


def collision_branch_name(
    *,
    base_branch_name: str,
    attempt: int,
) -> str:
    branch = f"{base_branch_name}-{attempt}"

    return trim_branch_name(
        branch
    )


def validate_branch_name(
    branch_name: str,
    *,
    base_branch: str,
) -> None:
    if branch_name == base_branch:
        raise BranchNameError(
            "Publication branch cannot be the base branch"
        )

    if branch_name in {
        "main",
        "master",
    }:
        raise BranchNameError(
            "Publication branch cannot be a default branch name"
        )

    if (
        not branch_name
        or branch_name.startswith("/")
        or branch_name.endswith("/")
        or branch_name.startswith("refs/")
        or ".." in branch_name
        or "@{" in branch_name
        or "\\" in branch_name
        or any(
            ord(char) < 32
            for char in branch_name
        )
    ):
        raise BranchNameError(
            "Unsafe branch name"
        )

    if re.search(
        r"[\s~^:?*\[]",
        branch_name,
    ):
        raise BranchNameError(
            "Unsafe branch name"
        )


def slugify(
    value: str,
) -> str:
    lowered = value.lower()
    cleaned = re.sub(
        r"[^a-z0-9]+",
        "-",
        lowered,
    ).strip("-")

    return cleaned[:48] or "change"


def trim_branch_name(
    branch_name: str,
) -> str:
    if len(branch_name) <= MAX_BRANCH_LENGTH:
        return branch_name

    prefix = "repopilot/"
    rest = branch_name[len(prefix):]
    return prefix + rest[: MAX_BRANCH_LENGTH - len(prefix)]
