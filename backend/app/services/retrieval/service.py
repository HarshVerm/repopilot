from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models.code_chunk import CodeChunk
from app.db.models.code_index import RepositoryFile
from app.services.chunking.chunker import (
    UnsafeRepositoryPathError,
    build_code_chunks_for_file,
    build_embedding_text,
)
from app.services.embeddings.client import (
    EmbeddingClient,
    OpenAIEmbeddingClient,
    validate_embedding_dimensions,
)
from app.services.hardening.validation import (
    validate_retrieval_request,
)
from app.services.retrieval.context import (
    MAX_CHUNKS_PER_FILE,
    apply_file_diversity,
    build_context_pack,
)
from app.services.retrieval.fusion import (
    reciprocal_rank_fusion,
)
from app.services.retrieval.lexical import (
    retrieve_lexical,
)
from app.services.retrieval.semantic import (
    retrieve_semantic,
)
from app.services.retrieval.structural import (
    retrieve_structural,
)


STRUCTURAL_K = 30
LEXICAL_K = 30
SEMANTIC_K = 30


def sanitize_retrieval_error(
    exc: Exception,
) -> str:
    return f"{exc.__class__.__name__}: semantic retrieval unavailable"


async def embed_chunk_texts(
    drafts,
    embedding_client: EmbeddingClient,
) -> tuple[list[list[float] | None], int, int]:
    embeddings: list[list[float] | None] = [
        None
        for _ in drafts
    ]
    embedded = 0
    failed = 0

    for start in range(
        0,
        len(drafts),
        embedding_client.batch_size,
    ):
        batch_drafts = drafts[
            start : start
            + embedding_client.batch_size
        ]
        texts = [
            build_embedding_text(draft)
            for draft in batch_drafts
        ]

        try:
            batch_embeddings = (
                await embedding_client.embed(
                    texts
                )
            )

            if len(batch_embeddings) != len(texts):
                raise RuntimeError(
                    "embedding provider returned an unexpected result count"
                )

            for offset, embedding in enumerate(
                batch_embeddings
            ):
                validate_embedding_dimensions(
                    embedding,
                    settings.embedding_dimensions,
                )
                embeddings[start + offset] = embedding
                embedded += 1
        except Exception:
            failed += len(batch_drafts)

    return (
        embeddings,
        embedded,
        failed,
    )


async def build_retrieval_index(
    *,
    workspace_id: str,
    repository_path: Path,
    db: AsyncSession,
    embedding_client: EmbeddingClient | None = None,
) -> dict:
    client = embedding_client or OpenAIEmbeddingClient()

    result = await db.execute(
        select(RepositoryFile)
        .options(
            selectinload(
                RepositoryFile.symbols
            )
        )
        .where(
            RepositoryFile.workspace_id
            == workspace_id
        )
        .order_by(
            RepositoryFile.file_path
        )
    )
    file_records = (
        result.scalars().unique().all()
    )

    await db.execute(
        delete(CodeChunk).where(
            CodeChunk.workspace_id
            == workspace_id
        )
    )

    drafts = []
    files_processed = 0
    files_failed = 0
    failures: list[dict[str, str]] = []

    for file_record in file_records:
        try:
            file_chunks = (
                build_code_chunks_for_file(
                    file_record,
                    repository_path,
                )
            )
        except (
            OSError,
            UnicodeDecodeError,
            UnsafeRepositoryPathError,
        ):
            files_failed += 1
            failures.append(
                {
                    "file_path": file_record.file_path,
                    "reason": "source file could not be safely read",
                }
            )
            continue

        files_processed += 1
        drafts.extend(file_chunks)

        if len(drafts) > settings.max_code_chunks:
            raise RuntimeError(
                "code chunk count exceeds configured limit"
            )

    (
        embeddings,
        chunks_embedded,
        chunks_embedding_failed,
    ) = await embed_chunk_texts(
        drafts,
        client,
    )

    for draft, embedding in zip(
        drafts,
        embeddings,
        strict=True,
    ):
        db.add(
            CodeChunk(
                workspace_id=workspace_id,
                file_id=draft.file_id,
                symbol_id=draft.symbol_id,
                chunk_type=draft.chunk_type,
                file_path=draft.file_path,
                language=draft.language,
                symbol_name=draft.symbol_name,
                symbol_kind=draft.symbol_kind,
                start_line=draft.start_line,
                end_line=draft.end_line,
                chunk_index=draft.chunk_index,
                content=draft.content,
                content_hash=draft.content_hash,
                embedding_model=client.model,
                embedding=embedding,
            )
        )

    await db.commit()

    return {
        "files_processed": files_processed,
        "files_failed": files_failed,
        "chunks_created": len(drafts),
        "chunks_embedded": chunks_embedded,
        "chunks_embedding_failed": chunks_embedding_failed,
        "failures": failures,
    }


async def hybrid_search(
    *,
    workspace_id: str,
    query: str,
    top_k: int,
    db: AsyncSession,
    embedding_client: EmbeddingClient | None = None,
    debug: bool = False,
) -> dict:
    client = embedding_client or OpenAIEmbeddingClient()
    stripped_query = query.strip()
    validate_retrieval_request(
        query=stripped_query,
        top_k=top_k,
    )

    structural = await retrieve_structural(
        db,
        workspace_id=workspace_id,
        query=stripped_query,
        limit=STRUCTURAL_K,
    )
    lexical = await retrieve_lexical(
        db,
        workspace_id=workspace_id,
        query=stripped_query,
        limit=LEXICAL_K,
    )

    semantic = []
    semantic_error = None

    try:
        semantic = await retrieve_semantic(
            db,
            workspace_id=workspace_id,
            query=stripped_query,
            limit=SEMANTIC_K,
            embedding_client=client,
        )
    except Exception as exc:
        semantic_error = sanitize_retrieval_error(
            exc
        )

    fused = reciprocal_rank_fusion(
        [
            structural,
            lexical,
            semantic,
        ]
    )
    final_results = apply_file_diversity(
        fused,
        top_k=top_k,
        max_chunks_per_file=MAX_CHUNKS_PER_FILE,
    )
    context = build_context_pack(
        query=stripped_query,
        candidates=final_results,
    )

    response = {
        "query": stripped_query,
        "results": [
            {
                "chunk_id": str(
                    candidate.chunk_id
                ),
                "file_path": candidate.file_path,
                "symbol_name": candidate.symbol_name,
                "symbol_kind": candidate.symbol_kind,
                "start_line": candidate.start_line,
                "end_line": candidate.end_line,
                "content": candidate.content,
                "score": candidate.score,
                "matched_by": list(
                    candidate.matched_by
                ),
            }
            for candidate in final_results
        ],
        "context": context,
        "debug": None,
    }

    if debug:
        response["debug"] = {
            "semantic_available": semantic_error is None,
            "semantic_error": semantic_error,
            "structural_ranked_ids": [
                str(candidate.chunk_id)
                for candidate in structural
            ],
            "lexical_ranked_ids": [
                str(candidate.chunk_id)
                for candidate in lexical
            ],
            "semantic_ranked_ids": [
                str(candidate.chunk_id)
                for candidate in semantic
            ],
            "fused_ranked_ids": [
                str(candidate.chunk_id)
                for candidate in fused
            ],
        }

    return response
