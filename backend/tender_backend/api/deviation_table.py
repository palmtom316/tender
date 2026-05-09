"""API routes for deviation table management (商务偏差表/技术偏差表)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.project_access import require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.bid_outline_repo import BidOutlineRepository

router = APIRouter(tags=["deviation-table"])
_repo = BidOutlineRepository()
_CHAPTER_PROJECT_QUERY = "SELECT project_id FROM bid_chapter WHERE id = %s"


class DeviationItem(BaseModel):
    """Single deviation item in the table."""
    seq_number: int
    procurement_clause_number: str
    procurement_clause: str
    response_clause: str
    deviation_note: str


class DeviationTableBody(BaseModel):
    """Deviation table data for a chapter."""
    has_deviation: bool = False
    items: list[DeviationItem] = []


@router.get("/bid-outline/chapters/{chapter_id}/deviation-table")
async def get_deviation_table(
    chapter_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> DeviationTableBody:
    """Get deviation table data for a chapter."""
    require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )

    chapter = _repo.get_chapter_by_id(conn, chapter_id=chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="bid chapter not found")

    metadata = chapter.get("metadata_json", {})
    deviation_data = metadata.get("deviation_table", {})

    return DeviationTableBody(
        has_deviation=deviation_data.get("has_deviation", False),
        items=[DeviationItem(**item) for item in deviation_data.get("items", [])]
    )


@router.put("/bid-outline/chapters/{chapter_id}/deviation-table")
async def update_deviation_table(
    chapter_id: UUID,
    payload: DeviationTableBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Update deviation table data for a chapter."""
    require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )

    # Get current chapter metadata
    chapter = _repo.get_chapter_by_id(conn, chapter_id=chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="bid chapter not found")

    # Update metadata with deviation table data
    metadata = chapter.get("metadata_json", {})
    metadata["deviation_table"] = payload.model_dump()

    # Update chapter
    row = _repo.update_chapter(
        conn,
        chapter_id=chapter_id,
        fields={"metadata_json": metadata}
    )

    if row is None:
        raise HTTPException(status_code=404, detail="bid chapter not found")

    return row
