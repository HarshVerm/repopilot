from app.core.config import settings
from app.services.chunking.tokenizer import (
    count_tokens,
)
from app.services.retrieval.candidates import (
    RetrievalCandidate,
)


MAX_CHUNKS_PER_FILE = 3


def estimate_context_chunk_tokens(
    candidate: RetrievalCandidate,
) -> int:
    metadata = (
        f"{candidate.file_path}\n"
        f"{candidate.symbol_name or ''}\n"
        f"{candidate.symbol_kind or ''}\n"
        f"{candidate.start_line}-{candidate.end_line}\n"
    )

    return count_tokens(
        metadata + candidate.content
    )


def apply_file_diversity(
    candidates: list[RetrievalCandidate],
    *,
    top_k: int,
    max_chunks_per_file: int = MAX_CHUNKS_PER_FILE,
) -> list[RetrievalCandidate]:
    selected: list[RetrievalCandidate] = []
    file_counts: dict[str, int] = {}

    for candidate in candidates:
        if len(selected) >= top_k:
            break

        count = file_counts.get(
            candidate.file_path,
            0,
        )

        if count >= max_chunks_per_file:
            continue

        file_counts[candidate.file_path] = count + 1
        selected.append(candidate)

    return selected


def build_context_pack(
    *,
    query: str,
    candidates: list[RetrievalCandidate],
    max_tokens: int = settings.max_context_tokens,
    max_chunks_per_file: int = MAX_CHUNKS_PER_FILE,
) -> dict:
    files: dict[str, dict] = {}
    file_counts: dict[str, int] = {}
    estimated_tokens = count_tokens(query)
    seen_chunk_ids = set()

    for candidate in candidates:
        if candidate.chunk_id in seen_chunk_ids:
            continue

        seen_chunk_ids.add(
            candidate.chunk_id
        )
        file_count = file_counts.get(
            candidate.file_path,
            0,
        )

        if file_count >= max_chunks_per_file:
            continue

        chunk_tokens = estimate_context_chunk_tokens(
            candidate
        )

        if chunk_tokens > max_tokens:
            continue

        if estimated_tokens + chunk_tokens > max_tokens:
            continue

        file_counts[candidate.file_path] = (
            file_count + 1
        )
        estimated_tokens += chunk_tokens

        file_entry = files.setdefault(
            candidate.file_path,
            {
                "path": candidate.file_path,
                "chunks": [],
            },
        )
        file_entry["chunks"].append(
            {
                "chunk_id": str(
                    candidate.chunk_id
                ),
                "symbol": candidate.symbol_name,
                "kind": candidate.symbol_kind,
                "start_line": candidate.start_line,
                "end_line": candidate.end_line,
                "content": candidate.content,
                "score": candidate.score,
                "matched_by": list(
                    candidate.matched_by
                ),
            }
        )

    return {
        "query": query,
        "estimated_tokens": estimated_tokens,
        "files": list(files.values()),
    }
