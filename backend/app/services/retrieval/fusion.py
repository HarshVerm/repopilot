from dataclasses import replace

from app.services.retrieval.candidates import (
    RetrievalCandidate,
    ordered_sources,
)


RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalCandidate]],
    *,
    k: int = RRF_K,
) -> list[RetrievalCandidate]:
    scores = {}
    candidates = {}
    matched_by = {}

    for ranked_list in ranked_lists:
        seen_in_list = set()

        for fallback_rank, candidate in enumerate(
            ranked_list,
            start=1,
        ):
            chunk_id = candidate.chunk_id

            if chunk_id in seen_in_list:
                continue

            seen_in_list.add(chunk_id)
            rank = candidate.rank or fallback_rank
            scores[chunk_id] = (
                scores.get(chunk_id, 0.0)
                + 1.0 / (k + rank)
            )

            if chunk_id not in candidates:
                candidates[chunk_id] = candidate

            matched_by.setdefault(
                chunk_id,
                set(),
            ).add(candidate.source)

    fused = [
        replace(
            candidate,
            score=scores[chunk_id],
            matched_by=ordered_sources(
                matched_by[chunk_id]
            ),
        )
        for chunk_id, candidate in candidates.items()
    ]

    return sorted(
        fused,
        key=lambda candidate: (
            -candidate.score,
            candidate.file_path,
            candidate.start_line,
            str(candidate.chunk_id),
        ),
    )
