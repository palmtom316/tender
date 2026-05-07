"""API routes for project requirements and human confirmation."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.db.repositories.requirement_match_repo import RequirementMatchRepository
from tender_backend.services.requirement_matching import build_requirement_matches
from tender_backend.services.requirement_grouping_service import build_requirement_workbench
from tender_backend.services.tender_constraint_service import TenderConstraintService
from tender_backend.db.repositories.clarification_repo import ClarificationRepository

router = APIRouter(tags=["requirements"])
_repo = RequirementRepository()
_match_repo = RequirementMatchRepository()
_constraint_service = TenderConstraintService()
_clarification_repo = ClarificationRepository()
_REQUIREMENT_PROJECT_QUERY = "SELECT project_id FROM project_requirement WHERE id = %s"


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


class BulkConfirmBody(BaseModel):
    requirement_ids: list[UUID]


class ClarificationCreateBody(BaseModel):
    round_no: int = 1
    clarification_type: str = "clarification"
    title: str
    source_file: str | None = None
    content_text: str = ""
    impact_json: dict | None = None
    status: str = "active"


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
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
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


@router.get("/projects/{project_id}/requirements/workbench")
async def get_requirement_workbench(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    rows = _repo.list_by_project(conn, project_id=project_id)
    return build_requirement_workbench(str(project_id), rows)


@router.get("/projects/{project_id}/requirements/download")
async def download_requirements(
    project_id: UUID,
    category: str | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    require_project_access(conn, project_id=project_id, user=user)
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


@router.post("/projects/{project_id}/constraint-set")
async def build_project_constraint_set(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _constraint_service.build_from_requirements(conn, project_id=project_id)


@router.get("/projects/{project_id}/constraint-set")
async def get_latest_project_constraint_set(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _constraint_service.latest(conn, project_id=project_id) or {"project_id": str(project_id), "items": []}


@router.post("/projects/{project_id}/clarifications")
async def create_project_clarification(
    project_id: UUID,
    payload: ClarificationCreateBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _clarification_repo.create(conn, project_id=project_id, fields=payload.model_dump())


@router.get("/projects/{project_id}/clarifications")
async def list_project_clarifications(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
    return _clarification_repo.list_by_project(conn, project_id=project_id)


@router.patch("/requirements/{requirement_id}")
async def update_requirement(
    requirement_id: UUID,
    payload: RequirementUpdateBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=requirement_id,
        query=_REQUIREMENT_PROJECT_QUERY,
        not_found_detail="requirement not found",
        user=user,
    )
    row = _repo.update(conn, requirement_id=requirement_id, fields=payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row


@router.post("/requirements/{requirement_id}/mark-hard")
async def mark_hard_constraint(
    requirement_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=requirement_id,
        query=_REQUIREMENT_PROJECT_QUERY,
        not_found_detail="requirement not found",
        user=user,
    )
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
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=requirement_id,
        query=_REQUIREMENT_PROJECT_QUERY,
        not_found_detail="requirement not found",
        user=user,
    )
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
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=requirement_id,
        query=_REQUIREMENT_PROJECT_QUERY,
        not_found_detail="requirement not found",
        user=user,
    )
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
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=requirement_id,
        query=_REQUIREMENT_PROJECT_QUERY,
        not_found_detail="requirement not found",
        user=user,
    )
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
    require_resource_project_access(
        conn,
        resource_id=requirement_id,
        query=_REQUIREMENT_PROJECT_QUERY,
        not_found_detail="requirement not found",
        user=user,
    )
    row = _repo.confirm(conn, requirement_id=requirement_id, confirmed_by=user.display_name)
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row


@router.post("/projects/{project_id}/requirements/bulk-confirm")
async def bulk_confirm_requirements(
    project_id: UUID,
    payload: BulkConfirmBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    rows = []
    for requirement_id in payload.requirement_ids:
        row = _repo.confirm_if_in_project(
            conn,
            project_id=project_id,
            requirement_id=requirement_id,
            confirmed_by=user.display_name,
        )
        if row is not None:
            rows.append(row)
    return {"project_id": str(project_id), "confirmed_count": len(rows), "requirements": rows}


@router.post("/requirements/{requirement_id}/reject")
async def reject_requirement(
    requirement_id: UUID,
    payload: RejectBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=requirement_id,
        query=_REQUIREMENT_PROJECT_QUERY,
        not_found_detail="requirement not found",
        user=user,
    )
    row = _repo.reject(conn, requirement_id=requirement_id, review_note=payload.review_note)
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row


@router.get("/projects/{project_id}/export-readiness")
async def check_export_readiness(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Check if all veto requirements are confirmed (export gate)."""
    require_project_access(conn, project_id=project_id, user=user)
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
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return build_requirement_matches(conn, project_id=project_id)


@router.get("/projects/{project_id}/requirement-matches")
async def list_requirement_matches(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
    return _match_repo.list_by_project(conn, project_id=project_id)
