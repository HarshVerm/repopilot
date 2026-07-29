import uuid

from app.services.retrieval.candidates import (
    RetrievalCandidate,
)
from app.services.retrieval.context import (
    apply_file_diversity,
    build_context_pack,
)
from app.services.retrieval.fusion import (
    reciprocal_rank_fusion,
)


def make_candidate(
    name: str,
    source: str,
    rank: int,
    file_path: str | None = None,
    content: str = "content",
) -> RetrievalCandidate:
    chunk_id = uuid.uuid5(
        uuid.NAMESPACE_DNS,
        name,
    )

    return RetrievalCandidate(
        chunk_id=chunk_id,
        file_path=file_path or f"{name}.ts",
        symbol_name=name,
        symbol_kind="function",
        start_line=rank,
        end_line=rank + 1,
        content=content,
        source=source,
        rank=rank,
    )


def test_reciprocal_rank_fusion_merges_duplicates_and_sources():
    fused = reciprocal_rank_fusion(
        [
            [
                make_candidate(
                    "A",
                    "structural",
                    1,
                ),
                make_candidate(
                    "C",
                    "structural",
                    2,
                ),
                make_candidate(
                    "F",
                    "structural",
                    3,
                ),
            ],
            [
                make_candidate(
                    "C",
                    "lexical",
                    1,
                ),
                make_candidate(
                    "A",
                    "lexical",
                    2,
                ),
                make_candidate(
                    "G",
                    "lexical",
                    3,
                ),
            ],
            [
                make_candidate(
                    "B",
                    "semantic",
                    1,
                ),
                make_candidate(
                    "A",
                    "semantic",
                    2,
                ),
                make_candidate(
                    "C",
                    "semantic",
                    3,
                ),
            ],
        ]
    )

    assert [
        candidate.symbol_name
        for candidate in fused[:3]
    ] == [
        "A",
        "C",
        "B",
    ]
    assert fused[0].matched_by == (
        "structural",
        "lexical",
        "semantic",
    )
    assert fused[1].matched_by == (
        "structural",
        "lexical",
        "semantic",
    )


def test_file_diversity_and_context_budget():
    candidates = [
        make_candidate(
            f"same-{index}",
            "lexical",
            index + 1,
            file_path="src/same.ts",
            content="word " * 5,
        )
        for index in range(5)
    ] + [
        make_candidate(
            "other",
            "semantic",
            6,
            file_path="src/other.ts",
            content="small",
        )
    ]

    diverse = apply_file_diversity(
        candidates,
        top_k=6,
        max_chunks_per_file=3,
    )
    context = build_context_pack(
        query="query",
        candidates=diverse,
        max_tokens=120,
        max_chunks_per_file=3,
    )

    assert [
        candidate.file_path
        for candidate in diverse
    ].count("src/same.ts") == 3
    assert any(
        file["path"] == "src/other.ts"
        for file in context["files"]
    )
    assert context["estimated_tokens"] <= 120
