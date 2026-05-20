"""API routes for bid outline planning."""

from __future__ import annotations

from uuid import UUID

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.bid_outline_repo import BidOutlineRepository
from tender_backend.services.bid_chapter_generation import generate_bid_chapter_draft
from tender_backend.services.ad_hoc_chapter_task_card import (
    build_initial_task_card,
    change_task_card_type,
    generate_task_card_outline,
    merge_task_card_metadata,
    update_task_card_answers,
    validate_task_card_ready_for_outline,
)
from tender_backend.services.bid_outline_planner import build_bid_outline
from tender_backend.services.outline_reconciliation_service import OutlineReconciliationService

router = APIRouter(tags=["bid-outline"])
_repo = BidOutlineRepository()
_outline_service = OutlineReconciliationService()
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


class AdHocTaskCardUpdateBody(BaseModel):
    answers: dict[str, Any] = {}
    chapter_type: str | None = None


class AdHocTaskCardConfirmOutlineBody(BaseModel):
    outline: list[dict[str, Any]]


def _load_bid_chapter(conn: Connection, *, project_id: UUID, chapter_id: UUID) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT * FROM bid_chapter WHERE id = %s AND project_id = %s",
            (chapter_id, project_id),
        ).fetchone()
    return dict(row) if row else None


def _load_chapter_requirements(conn: Connection, *, chapter_id: UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT pr.*
            FROM bid_chapter_requirement bcr
            JOIN project_requirement pr ON pr.id = bcr.requirement_id
            WHERE bcr.bid_chapter_id = %s
            ORDER BY pr.created_at
            """,
            (chapter_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _save_ad_hoc_task_card(conn: Connection, *, project_id: UUID, chapter_id: UUID, card: dict[str, Any]) -> dict[str, Any]:
    chapter = _load_bid_chapter(conn, project_id=project_id, chapter_id=chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    metadata = merge_task_card_metadata(chapter.get("metadata_json") or {}, card)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE bid_chapter
            SET metadata_json = %s, updated_at = now()
            WHERE id = %s AND project_id = %s
            """,
            (Jsonb(metadata), chapter_id, project_id),
        )
    conn.commit()
    return card


def _ad_hoc_allowed(chapter: dict) -> bool:
    metadata = chapter.get("metadata_json") or {}
    return bool(metadata.get("ad_hoc_required")) or metadata.get("template_match_status") == "missing"


def _task_card_response(chapter_id: UUID, card: dict[str, Any]) -> dict:
    return {"chapter_id": str(chapter_id), "card": card}


def _chapter_card(chapter: dict) -> dict[str, Any] | None:
    metadata = chapter.get("metadata_json") or {}
    card = metadata.get("ad_hoc_task_card")
    return dict(card) if isinstance(card, dict) else None


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


@router.get("/projects/{project_id}/bid-outline/reconciliation")
async def preview_bid_outline_reconciliation(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _outline_service.preview(conn, project_id=project_id)


@router.post("/projects/{project_id}/bid-outline/confirm")
async def confirm_bid_outline(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        return _outline_service.confirm(conn, project_id=project_id, confirmed_by=user.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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


@router.get("/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card")
async def get_ad_hoc_task_card(
    project_id: UUID,
    chapter_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn, resource_id=chapter_id, query=_CHAPTER_PROJECT_QUERY, not_found_detail="bid chapter not found", user=user
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    chapter = _load_bid_chapter(conn, project_id=project_id, chapter_id=chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    existing = _chapter_card(chapter)
    if existing is not None:
        return _task_card_response(chapter_id, existing)
    if not _ad_hoc_allowed(chapter):
        raise HTTPException(status_code=409, detail="chapter is not marked as ad hoc")
    requirements = _load_chapter_requirements(conn, chapter_id=chapter_id)
    card = build_initial_task_card(chapter_title=str(chapter.get("chapter_title") or ""), source_requirements=requirements)
    saved = _save_ad_hoc_task_card(conn, project_id=project_id, chapter_id=chapter_id, card=card)
    return _task_card_response(chapter_id, saved)


@router.patch("/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card")
async def patch_ad_hoc_task_card(
    project_id: UUID,
    chapter_id: UUID,
    payload: AdHocTaskCardUpdateBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn, resource_id=chapter_id, query=_CHAPTER_PROJECT_QUERY, not_found_detail="bid chapter not found", user=user
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    chapter = _load_bid_chapter(conn, project_id=project_id, chapter_id=chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    card = _chapter_card(chapter)
    if card is None:
        raise HTTPException(status_code=404, detail="ad hoc task card not found")
    try:
        if payload.chapter_type:
            card = change_task_card_type(card, chapter_type=payload.chapter_type)
        if payload.answers:
            card = update_task_card_answers(card, answers=payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    saved = _save_ad_hoc_task_card(conn, project_id=project_id, chapter_id=chapter_id, card=card)
    return _task_card_response(chapter_id, saved)


@router.post("/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/outline")
async def generate_ad_hoc_task_card_outline(
    project_id: UUID,
    chapter_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn, resource_id=chapter_id, query=_CHAPTER_PROJECT_QUERY, not_found_detail="bid chapter not found", user=user
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    chapter = _load_bid_chapter(conn, project_id=project_id, chapter_id=chapter_id)
    card = _chapter_card(chapter or {})
    if card is None:
        raise HTTPException(status_code=404, detail="ad hoc task card not found")
    if card.get("status") in {"outline_ready", "outline_confirmed", "draft_ready"}:
        raise HTTPException(status_code=409, detail="outline already generated or draft exists")
    try:
        card["outline"] = generate_task_card_outline(card)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    card["status"] = "outline_ready"
    saved = _save_ad_hoc_task_card(conn, project_id=project_id, chapter_id=chapter_id, card=card)
    return _task_card_response(chapter_id, saved)


@router.post("/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/confirm-outline")
async def confirm_ad_hoc_task_card_outline(
    project_id: UUID,
    chapter_id: UUID,
    payload: AdHocTaskCardConfirmOutlineBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn, resource_id=chapter_id, query=_CHAPTER_PROJECT_QUERY, not_found_detail="bid chapter not found", user=user
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    chapter = _load_bid_chapter(conn, project_id=project_id, chapter_id=chapter_id)
    card = _chapter_card(chapter or {})
    if card is None:
        raise HTTPException(status_code=404, detail="ad hoc task card not found")
    if card.get("status") != "outline_ready":
        raise HTTPException(status_code=409, detail="outline must be generated before confirmation")
    if not payload.outline:
        raise HTTPException(status_code=422, detail="outline must not be empty")
    readiness = validate_task_card_ready_for_outline(card)
    if not readiness.get("ready"):
        raise HTTPException(status_code=409, detail="required task card inputs are missing")
    card["outline"] = payload.outline
    card["status"] = "outline_confirmed"
    saved = _save_ad_hoc_task_card(conn, project_id=project_id, chapter_id=chapter_id, card=card)
    return _task_card_response(chapter_id, saved)


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
