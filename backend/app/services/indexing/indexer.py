from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.code_index import (
    CodeSymbol,
    RepositoryFile,
)

from app.services.indexing.parser import (
    parse_source,
    supports_ast_parsing,
)
from app.services.indexing.scanner import (
    calculate_sha256,
    scan_repository,
    RepositoryLimitError,
)
from app.services.indexing.symbols import (
    extract_symbols,
)


def file_failure(
    file_path: str,
    reason: str,
) -> dict[str, str]:
    return {
        "file_path": file_path,
        "reason": reason,
    }


async def index_repository(
    workspace_id: str,
    repository_path: Path,
    db: AsyncSession,
):

    source_files = scan_repository(
        repository_path
    )

    if len(source_files) > settings.max_indexed_files:
        raise RepositoryLimitError(
            "indexed source file count exceeds configured limit"
        )

    # MVP: replace previous index
    await db.execute(
        delete(RepositoryFile).where(
            RepositoryFile.workspace_id
            == workspace_id
        )
    )

    files_indexed = 0
    files_failed = 0
    symbols_indexed = 0
    failures: list[dict[str, str]] = []

    for source_file in source_files:

        try:
            source = (
                source_file.absolute_path
                .read_bytes()
            )
            sha256 = calculate_sha256(
                source
            )
        except OSError:
            files_failed += 1
            failures.append(
                file_failure(
                    source_file.relative_path,
                    "source file could not be read",
                )
            )
            continue

        symbols = []
        if supports_ast_parsing(
            source_file.language
        ):
            try:
                tree = parse_source(
                    source_file.language,
                    source,
                )

                symbols = extract_symbols(
                    source_file.language,
                    source,
                    tree,
                )
            except (RuntimeError, ValueError):
                files_failed += 1
                failures.append(
                    file_failure(
                        source_file.relative_path,
                        "source file could not be parsed",
                    )
                )
                continue

        if symbols_indexed + len(symbols) > settings.max_symbol_count:
            raise RepositoryLimitError(
                "repository symbol count exceeds configured limit"
            )

        file_record = RepositoryFile(
            workspace_id=workspace_id,
            file_path=(
                source_file.relative_path
            ),
            language=source_file.language,
            size_bytes=(
                source_file.size_bytes
            ),
            sha256=sha256,
        )

        db.add(file_record)

        await db.flush()

        for symbol in symbols:

            db.add(
                CodeSymbol(
                    file_id=file_record.id,
                    kind=symbol.kind,
                    name=symbol.name,
                    start_line=(
                        symbol.start_line
                    ),
                    end_line=(
                        symbol.end_line
                    ),
                )
            )

        files_indexed += 1
        symbols_indexed += len(symbols)

    await db.commit()

    return {
        "files_discovered": len(source_files),
        "files_indexed": files_indexed,
        "files_failed": files_failed,
        "symbols_indexed": symbols_indexed,
        "failures": failures,
    }
