"""API routes for qualification-business and technical generation gates."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.business_bid_assembler import BusinessBidAssembler
from tender_backend.services.technical_chapter_context import TechnicalChapterContextBuilder
from tender_backend.services.technical_bid_writer import TechnicalBidWriter


router = APIRouter(tags=["bid-generation"])
_business_assembler = BusinessBidAssembler()
_technical_writer = TechnicalBidWriter()
_context_builder = TechnicalChapterContextBuilder()
_CHAPTER_PROJECT_QUERY = "SELECT project_id FROM bid_chapter WHERE id = %s"


class TechnicalGenerateBody(BaseModel):
    rewrite_note: str | None = None


@router.post("/projects/{project_id}/business-bid/assemble")
async def assemble_business_bid(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        return _business_assembler.assemble(conn, project_id=project_id, created_by=user.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projects/{project_id}/technical-bid/writing-plan")
async def get_technical_writing_plan(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        return _technical_writer.create_writing_plan(conn, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/projects/{project_id}/technical-bid/chapters/{chapter_id}/generate")
async def generate_technical_chapter(
    project_id: UUID,
    chapter_id: UUID,
    payload: TechnicalGenerateBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    try:
        return _technical_writer.generate_chapter(
            conn,
            project_id=project_id,
            chapter_id=chapter_id,
            rewrite_note=payload.rewrite_note if payload else None,
            created_by=user.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projects/{project_id}/technical-bid/chapters/{chapter_id}/context")
async def get_technical_chapter_context(
    project_id: UUID,
    chapter_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    try:
        return _context_builder.build(conn, project_id=project_id, chapter_id=chapter_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
