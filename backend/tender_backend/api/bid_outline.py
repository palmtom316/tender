"""API routes for bid outline planning."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.bid_outline_repo import BidOutlineRepository
from tender_backend.services.bid_chapter_generation import generate_bid_chapter_draft
from tender_backend.services.bid_outline_planner import build_bid_outline

router = APIRouter(tags=["bid-outline"])
_repo = BidOutlineRepository()
_CHAPTER_PROJECT_QUERY = "SELECT project_id FROM bid_chapter WHERE id = %s"


class ChapterUpdateBody(BaseModel):
    chapter_code: str | None = None
    chapter_title: str | None = None
    volume_type: str | None = None
    sort_order: int | None = None
    outline_md: str | None = None
    metadata_json: dict | None = None


class ChapterRequirementMappingBody(BaseModel):
    requirement_ids: list[UUID]
    mapping_reason: str = "人工调整章节约束映射"
    priority_level: str = "normal"


class ChapterGenerateBody(BaseModel):
    rewrite_note: str | None = None


@router.post("/projects/{project_id}/bid-outline")
async def generate_bid_outline(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return build_bid_outline(conn, project_id=project_id)


@router.get("/projects/{project_id}/bid-outline")
async def get_latest_bid_outline(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    row = _repo.get_latest_by_project(conn, project_id=project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="bid outline not found")
    return row


@router.patch("/bid-outline/chapters/{chapter_id}")
async def update_bid_chapter(
    chapter_id: UUID,
    payload: ChapterUpdateBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )
    row = _repo.update_chapter(conn, chapter_id=chapter_id, fields=payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    return row


@router.put("/bid-outline/chapters/{chapter_id}/requirements")
async def replace_bid_chapter_requirements(
    chapter_id: UUID,
    payload: ChapterRequirementMappingBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )
    row = _repo.replace_chapter_requirements(
        conn,
        chapter_id=chapter_id,
        requirement_ids=payload.requirement_ids,
        mapping_reason=payload.mapping_reason,
        priority_level=payload.priority_level,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    return row


@router.post("/projects/{project_id}/bid-chapters/{chapter_id}/generate")
async def generate_bid_chapter(
    project_id: UUID,
    chapter_id: UUID,
    payload: ChapterGenerateBody | None = None,
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
        return generate_bid_chapter_draft(
            conn,
            project_id=project_id,
            chapter_id=chapter_id,
            rewrite_note=payload.rewrite_note if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
