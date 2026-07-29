from pathlib import Path

import pytest

from app.services.changes.editor import (
    PatchSecurityError,
    RepoPilotPatchEditor,
)
from tests.coding_fixtures import (
    create_coding_fixture_repo,
    fixed_searchbox_content,
)


def make_editor(
    repo: Path,
    allowed_files: set[str] | None = None,
) -> RepoPilotPatchEditor:
    return RepoPilotPatchEditor(
        repository_path=repo,
        allowed_files=allowed_files
        or {
            "src/components/SearchBox.tsx"
        },
    )


def test_editor_updates_only_allowed_existing_files(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    create_coding_fixture_repo(repo)
    editor = make_editor(repo)

    result = editor.update_file(
        path="src/components/SearchBox.tsx",
        content=fixed_searchbox_content(),
    )

    assert result == {
        "path": "src/components/SearchBox.tsx",
        "updated": True,
    }
    assert "debouncedQuery" in (
        repo / "src/components/SearchBox.tsx"
    ).read_text(encoding="utf-8")
    assert editor.operations_accepted == 1


def test_editor_creates_only_an_explicitly_approved_new_file(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    create_coding_fixture_repo(repo)
    editor = RepoPilotPatchEditor(
        repository_path=repo,
        allowed_files={
            "tests/new-test.txt"
        },
        creatable_files={
            "tests/new-test.txt"
        },
    )
    (repo / "tests").mkdir()

    result = editor.create_file(
        path="tests/new-test.txt",
        content="new test fixture\n",
    )

    assert result == {
        "path": "tests/new-test.txt",
        "created": True,
    }
    assert (
        repo / "tests/new-test.txt"
    ).read_text(encoding="utf-8") == "new test fixture\n"
    assert editor.operations_accepted == 1

    with pytest.raises(
        PatchSecurityError
    ):
        editor.create_file(
            path="tests/not-approved.txt",
            content="bad\n",
        )


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "/absolute.txt",
        ".env",
        "package.json",
        "missing-parent/new.txt",
    ],
)
def test_editor_rejects_unsafe_approved_new_file_paths(
    tmp_path: Path,
    path: str,
):
    repo = tmp_path / "repo"
    create_coding_fixture_repo(repo)
    editor = RepoPilotPatchEditor(
        repository_path=repo,
        allowed_files={
            path
        },
        creatable_files={
            path
        },
    )

    with pytest.raises(
        PatchSecurityError
    ):
        editor.create_file(
            path=path,
            content="bad\n",
        )


def test_editor_rejects_symlink_at_approved_new_file_path(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    create_coding_fixture_repo(repo)
    outside = tmp_path / "outside.txt"
    outside.write_text(
        "secret\n",
        encoding="utf-8",
    )
    (repo / "new.txt").symlink_to(
        outside
    )
    editor = RepoPilotPatchEditor(
        repository_path=repo,
        allowed_files={
            "new.txt"
        },
        creatable_files={
            "new.txt"
        },
    )

    with pytest.raises(
        PatchSecurityError
    ):
        editor.create_file(
            path="new.txt",
            content="overwrite\n",
        )

    assert outside.read_text(
        encoding="utf-8"
    ) == "secret\n"


@pytest.mark.parametrize(
    "path",
    [
        "../../outside.py",
        "../../../etc/passwd",
        "/absolute/path/file.ts",
        "src/../../secret.txt",
    ],
)
def test_editor_rejects_traversal_and_absolute_paths(
    tmp_path: Path,
    path: str,
):
    repo = tmp_path / "repo"
    create_coding_fixture_repo(repo)
    editor = make_editor(
        repo,
        {
            path
        },
    )

    with pytest.raises(
        PatchSecurityError
    ):
        editor.update_file(
            path=path,
            content="bad",
        )


def test_editor_rejects_sensitive_and_dependency_files(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    create_coding_fixture_repo(repo)
    (repo / ".env").write_text(
        "SECRET=true\n",
        encoding="utf-8",
    )
    (repo / "package.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    editor = make_editor(
        repo,
        {
            ".env",
            "package.json",
        },
    )

    for path in [
        ".env",
        "package.json",
    ]:
        with pytest.raises(
            PatchSecurityError
        ):
            editor.update_file(
                path=path,
                content="bad",
            )


def test_editor_rejects_symlinks_inside_and_outside_repository(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    create_coding_fixture_repo(repo)
    outside = tmp_path / "outside.ts"
    outside.write_text(
        "secret\n",
        encoding="utf-8",
    )
    (repo / "src/outside-link.ts").symlink_to(
        outside
    )
    (repo / "src/inside-link.ts").symlink_to(
        repo / "src/hooks/useDebounce.ts"
    )
    editor = make_editor(
        repo,
        {
            "src/outside-link.ts",
            "src/inside-link.ts",
        },
    )

    for path in [
        "src/outside-link.ts",
        "src/inside-link.ts",
    ]:
        with pytest.raises(
            PatchSecurityError
        ):
            editor.update_file(
                path=path,
                content="bad",
            )

    assert outside.read_text(
        encoding="utf-8"
    ) == "secret\n"
