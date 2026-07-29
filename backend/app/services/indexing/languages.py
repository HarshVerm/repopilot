from pathlib import Path


LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


def detect_language(path: Path) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(
        path.suffix.lower()
    )