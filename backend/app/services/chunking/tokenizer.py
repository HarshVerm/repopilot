"""Split source text into overlapping, line-aware token-budget windows."""

from dataclasses import dataclass
from functools import lru_cache
import re

import tiktoken


@dataclass(frozen=True)
class TokenSplit:
    """Hold one text window and its one-based source line range."""

    content: str
    start_line: int
    end_line: int


@lru_cache(maxsize=1)
def get_encoding():
    """Return the primary tokenizer, falling back to a deterministic lexer."""
    try:
        return tiktoken.get_encoding(
            "cl100k_base"
        )
    except Exception:
        return SimpleEncoding()


class SimpleEncoding:
    """Provide a small reversible tokenizer when tiktoken is unavailable."""

    def encode(
        self,
        text: str,
    ) -> list[str]:
        """Tokenize text into whitespace, identifiers, numbers, and symbols."""
        return re.findall(
            r"\s+|[A-Za-z_][A-Za-z0-9_]*|\d+|[^\s]",
            text,
        )

    def decode(
        self,
        tokens: list[str],
    ) -> str:
        """Reassemble fallback tokens without changing their source text."""
        return "".join(tokens)


def count_tokens(
    text: str,
) -> int:
    """Count tokens with the same encoding used by the chunking pipeline."""
    if not text:
        return 0

    return len(
        get_encoding().encode(text)
    )


def split_long_line(
    line: str,
    line_number: int,
    max_tokens: int,
    overlap_tokens: int,
) -> list[TokenSplit]:
    """Window a single oversized line while preserving its line number."""
    encoding = get_encoding()
    tokens = encoding.encode(line)
    step = max(
        1,
        max_tokens - overlap_tokens,
    )
    splits: list[TokenSplit] = []

    for start in range(
        0,
        len(tokens),
        step,
    ):
        token_window = tokens[
            start : start + max_tokens
        ]
        if not token_window:
            continue

        splits.append(
            TokenSplit(
                content=encoding.decode(
                    token_window
                ),
                start_line=line_number,
                end_line=line_number,
            )
        )

        if start + max_tokens >= len(tokens):
            break

    return splits


def select_overlap_lines(
    lines: list[tuple[int, str, int]],
    overlap_tokens: int,
) -> list[tuple[int, str, int]]:
    """Select trailing whole lines to carry into the next text window."""
    if overlap_tokens <= 0:
        return []

    selected: list[tuple[int, str, int]] = []
    total_tokens = 0

    for item in reversed(lines):
        item_tokens = item[2]

        if total_tokens + item_tokens > overlap_tokens:
            break

        selected.append(item)
        total_tokens += item_tokens

    return list(reversed(selected))


def split_text_by_token_budget(
    text: str,
    max_tokens: int,
    overlap_tokens: int = 0,
    start_line: int = 1,
) -> list[TokenSplit]:
    """Create bounded chunks with overlap and accurate source line ranges."""
    if max_tokens <= 0:
        raise ValueError(
            "max_tokens must be greater than zero"
        )

    if overlap_tokens < 0:
        raise ValueError(
            "overlap_tokens must not be negative"
        )

    if overlap_tokens >= max_tokens:
        raise ValueError(
            "overlap_tokens must be smaller than max_tokens"
        )

    if not text:
        return []

    splits: list[TokenSplit] = []
    current: list[tuple[int, str, int]] = []
    current_tokens = 0

    # Purpose: Handle flush current for the code chunking workflow.
    def flush_current() -> None:
        nonlocal current
        nonlocal current_tokens

        if not current:
            return

        splits.append(
            TokenSplit(
                content="".join(
                    item[1]
                    for item in current
                ),
                start_line=current[0][0],
                end_line=current[-1][0],
            )
        )

        current = []
        current_tokens = 0

    for offset, line in enumerate(
        text.splitlines(keepends=True)
    ):
        line_number = start_line + offset
        line_tokens = count_tokens(line)

        if line_tokens > max_tokens:
            flush_current()
            splits.extend(
                split_long_line(
                    line=line,
                    line_number=line_number,
                    max_tokens=max_tokens,
                    overlap_tokens=overlap_tokens,
                )
            )
            continue

        if (
            current
            and current_tokens + line_tokens
            > max_tokens
        ):
            previous = current
            flush_current()

            current = select_overlap_lines(
                previous,
                overlap_tokens,
            )
            current_tokens = sum(
                item[2]
                for item in current
            )

            while (
                current
                and current_tokens + line_tokens
                > max_tokens
            ):
                removed = current.pop(0)
                current_tokens -= removed[2]

        current.append(
            (
                line_number,
                line,
                line_tokens,
            )
        )
        current_tokens += line_tokens

    flush_current()

    return splits
