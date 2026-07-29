import subprocess
from pathlib import Path
from types import SimpleNamespace

from app.services.indexing import scanner
from app.services.indexing.scanner import (
    scan_repository,
)


def init_git_repo(
    repo_path: Path,
) -> None:
    subprocess.run(
        ["git", "init", "-q"],
        cwd=repo_path,
        check=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        check=True,
    )


def write_file(
    repo_path: Path,
    relative_path: str,
    content: bytes,
) -> Path:
    path = repo_path / relative_path
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_bytes(content)
    return path


def scanned_paths(
    repo_path: Path,
) -> set[str]:
    return {
        source_file.relative_path
        for source_file in scan_repository(repo_path)
    }


def test_scanner_indexes_normal_tracked_file(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    content = b"def search_items(query):\n    pass\n"
    write_file(
        repo,
        "src/search.py",
        content,
    )
    init_git_repo(repo)

    files = scan_repository(repo)

    assert len(files) == 1
    assert files[0].relative_path == "src/search.py"
    assert files[0].size_bytes == len(content)


def test_scanner_includes_tracked_text_and_markdown_files(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "notes.txt",
        b"plain text repository context\n",
    )
    write_file(
        repo,
        "README.md",
        b"# Repository context\n",
    )
    init_git_repo(repo)

    files = {
        source_file.relative_path: source_file.language
        for source_file in scan_repository(repo)
    }

    assert files == {
        "README.md": "markdown",
        "notes.txt": "text",
    }


def test_scanner_skips_symlinks_inside_and_outside_repo(
    tmp_path: Path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_bytes(
        b"def outside_secret():\n    pass\n"
    )
    write_file(
        repo,
        "src/target.py",
        b"def target():\n    pass\n",
    )
    (repo / "src" / "inside_link.py").symlink_to(
        repo / "src" / "target.py"
    )
    (repo / "src" / "outside_link.py").symlink_to(
        outside
    )
    init_git_repo(repo)

    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path):
        if path.resolve() == outside.resolve():
            raise AssertionError(
                "scanner read outside symlink target"
            )

        return original_read_bytes(path)

    monkeypatch.setattr(
        Path,
        "read_bytes",
        guarded_read_bytes,
    )

    assert scanned_paths(repo) == {
        "src/target.py"
    }


def test_scanner_rejects_traversal_paths(
    tmp_path: Path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "src/search.ts",
        b"export function search() {}\n",
    )
    outside = tmp_path / "outside.ts"
    outside.write_bytes(
        b"export function outside() {}\n"
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            stdout=(
                b"../outside.ts\0"
                b"src/search.ts\0"
            )
        )

    monkeypatch.setattr(
        scanner.subprocess,
        "run",
        fake_run,
    )

    assert scanned_paths(repo) == {
        "src/search.ts"
    }


def test_scanner_excludes_dependency_and_build_directories(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    included = [
        "src/search.ts",
        "src/builders/index.ts",
        "src/distribution/utils.ts",
    ]
    excluded = [
        "node_modules/lib/index.ts",
        "dist/index.js",
        "build/output.js",
        ".next/server/app.js",
        "coverage/report.js",
        "vendor/package/index.ts",
        "src/generated.min.js",
    ]

    for relative_path in included:
        write_file(
            repo,
            relative_path,
            b"export function included() {}\n",
        )

    for relative_path in excluded:
        write_file(
            repo,
            relative_path,
            b"export function excluded() {}\n",
        )

    init_git_repo(repo)

    paths = scanned_paths(repo)

    assert set(included).issubset(paths)
    assert not set(excluded).intersection(paths)
