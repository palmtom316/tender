from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from tender_backend.core.config import get_settings
from tender_backend.db.pool import get_pool
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.search_service.index_manager import (
    CLAUSE_INDEX_MAPPINGS,
    INDEX_SETTINGS,
    IndexManager,
)

_repo = StandardRepository()


def build_clause_index_docs(standard: dict, clauses: list[dict]) -> list[tuple[str, dict]]:
    docs: list[tuple[str, dict]] = []
    for clause in clauses:
        doc_id = str(clause["id"])
        docs.append((doc_id, {
            "standard_id": str(standard["id"]),
            "standard_code": standard.get("standard_code"),
            "clause_id": doc_id,
            "clause_no": clause.get("clause_no"),
            "clause_title": clause.get("clause_title"),
            "clause_text": clause.get("clause_text"),
            "summary": clause.get("summary"),
            "tags": clause.get("tags", []),
            "specialty": standard.get("specialty"),
        }))
    return docs


async def reindex_standard_clauses(*, conn, standard_id: UUID) -> int:
    standard = _repo.get_standard(conn, standard_id)
    if not standard:
        raise ValueError(f"Standard not found: {standard_id}")

    clauses = _repo.list_clauses(conn, standard_id=standard_id)
    if not clauses:
        return 0

    manager = IndexManager()
    await manager.create_index("clause_index", {**INDEX_SETTINGS, **CLAUSE_INDEX_MAPPINGS})
    docs = build_clause_index_docs(standard, clauses)
    return await manager.bulk_index("clause_index", docs)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("Usage: python -m tender_backend.tools.reindex_standard_clauses <standard_id>")
        return 2

    standard_id = UUID(argv[0])
    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)

    with pool.connection() as conn:
        count = asyncio.run(reindex_standard_clauses(conn=conn, standard_id=standard_id))

    print(f"Indexed {count} clauses for standard {standard_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
