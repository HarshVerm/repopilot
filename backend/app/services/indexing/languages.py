"""Map repository file extensions to the languages supported by indexing."""

from pathlib import Path


LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".txt": "text",
    ".md": "markdown",
    ".markdown": "markdown",
}


def detect_language(path: Path) -> str | None:
    """Return the canonical index language for a path, if it is supported."""
    return LANGUAGE_BY_EXTENSION.get(
        path.suffix.lower()
    )
