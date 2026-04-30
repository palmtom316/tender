"""API routes for project requirements and human confirmation."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.security import CurrentUser, Role, get_current_user, require_role
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.db.repositories.requirement_match_repo import RequirementMatchRepository
from tender_backend.services.requirement_matching import build_requirement_matches

router = APIRouter(tags=["requirements"])
_repo = RequirementRepository()
_match_repo = RequirementMatchRepository()


class ConfirmBody(BaseModel):
    confirmed: bool = True


class RequirementUpdateBody(BaseModel):
    category: str | None = None
    title: str | None = None
    requirement_text: str | None = None
    source_text: str | None = None
    source_file: str | None = None
    source_locator: str | None = None
    confidence: float | None = None
    is_veto: bool | None = None
    is_hard_constraint: bool | None = None
    requires_human_confirm: bool | None = None
    human_confirmed: bool | None = None
    ignored_for_pricing: bool | None = None
    applies_to_chapter: str | None = None
    review_status: str | None = None
    review_note: str | None = None
    source_metadata: dict | None = None


class RejectBody(BaseModel):
    review_note: str | None = None


class RequirementMergeBody(BaseModel):
    source_requirement_ids: list[UUID]


class RequirementSplitBody(BaseModel):
    parts: list[RequirementUpdateBody]


@router.get("/projects/{project_id}/requirements")
async def list_requirements(
    project_id: UUID,
    category: str | None = None,
    review_status: str | None = None,
    human_confirmed: bool | None = None,
    requires_human_confirm: bool | None = None,
    is_veto: bool | None = None,
    is_hard_constraint: bool | None = None,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return _repo.list_by_project(
        conn,
        project_id=project_id,
        category=category,
        review_status=review_status,
        human_confirmed=human_confirmed,
        requires_human_confirm=requires_human_confirm,
        is_veto=is_veto,
        is_hard_constraint=is_hard_constraint,
    )


@router.get("/projects/{project_id}/requirements/download")
async def download_requirements(
    project_id: UUID,
    category: str | None = None,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> Response:
    rows = _repo.list_by_project(conn, project_id=project_id, category=category)
    payload = {
        "project_id": str(project_id),
        "category": category,
        "count": len(rows),
        "priority_policy": "tender_extracted_requirements_override_template",
        "requirements": rows,
    }
    content = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    suffix = f"-{category}" if category else ""
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="project-{project_id}-requirements{suffix}.json"'},
    )


@router.patch("/requirements/{requirement_id}")
async def update_requirement(
    requirement_id: UUID,
    payload: RequirementUpdateBody,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    row = _repo.update(conn, requirement_id=requirement_id, fields=payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row


@router.post("/requirements/{requirement_id}/mark-hard")
async def mark_hard_constraint(
    requirement_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    row = _repo.update(
        conn,
        requirement_id=requirement_id,
        fields={"is_hard_constraint": True, "requires_human_confirm": True},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row


@router.post("/requirements/{requirement_id}/mark-special")
async def mark_special_requirement(
    requirement_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    row = _repo.update(
        conn,
        requirement_id=requirement_id,
        fields={"category": "special", "is_hard_constraint": True, "requires_human_confirm": True},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row


@router.post("/requirements/{requirement_id}/merge")
async def merge_requirements(
    requirement_id: UUID,
    payload: RequirementMergeBody,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    row = _repo.merge(
        conn,
        target_requirement_id=requirement_id,
        source_requirement_ids=payload.source_requirement_ids,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found or source requirements are invalid")
    return row


@router.post("/requirements/{requirement_id}/split")
async def split_requirement(
    requirement_id: UUID,
    payload: RequirementSplitBody,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    existing = _repo.update(conn, requirement_id=requirement_id, fields={"review_status": "split"})
    if existing is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    parts = []
    for part in payload.parts:
        values = part.model_dump(exclude_unset=True)
        values.setdefault("category", existing["category"])
        values.setdefault("title", existing["title"])
        values.setdefault("source_text", values.get("requirement_text") or existing.get("source_text"))
        values.setdefault("source_file", existing.get("source_file"))
        values.setdefault("source_locator", existing.get("source_locator"))
        values.setdefault("confidence", existing.get("confidence"))
        values.setdefault("is_veto", existing.get("is_veto", False))
        values.setdefault("is_hard_constraint", existing.get("is_hard_constraint", False))
        values.setdefault("requires_human_confirm", True)
        values.setdefault("ignored_for_pricing", existing.get("ignored_for_pricing", False))
        metadata = dict(existing.get("source_metadata") or {})
        metadata["split_from_requirement_id"] = str(requirement_id)
        values.setdefault("source_metadata", metadata)
        parts.append(values)
    created = _repo.create_many(conn, project_id=existing["project_id"], requirements=parts)
    return {"source_requirement": existing, "created_count": len(created), "requirements": created}


@router.post("/requirements/{requirement_id}/confirm")
async def confirm_requirement(
    requirement_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    row = _repo.confirm(conn, requirement_id=requirement_id, confirmed_by=user.display_name)
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row


@router.post("/requirements/{requirement_id}/reject")
async def reject_requirement(
    requirement_id: UUID,
    payload: RejectBody,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    row = _repo.reject(conn, requirement_id=requirement_id, review_note=payload.review_note)
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row


@router.get("/projects/{project_id}/export-readiness")
async def check_export_readiness(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Check if all veto requirements are confirmed (export gate)."""
    unconfirmed = _repo.unconfirmed_veto_count(conn, project_id=project_id)
    return {
        "project_id": str(project_id),
        "veto_confirmed": unconfirmed == 0,
        "unconfirmed_veto_count": unconfirmed,
    }


@router.post("/projects/{project_id}/match-requirements")
async def match_project_requirements(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    return build_requirement_matches(conn, project_id=project_id)


@router.get("/projects/{project_id}/requirement-matches")
async def list_requirement_matches(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return _match_repo.list_by_project(conn, project_id=project_id)
