"""API routes for compliance matrix."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.compliance_check_service import ComplianceCheckService
from tender_backend.services.review_service.compliance_matrix import build_compliance_matrix

router = APIRouter(tags=["compliance"])
_check_service = ComplianceCheckService()
_FINDING_PROJECT_QUERY = "SELECT project_id FROM compliance_check_finding WHERE id = %s"


class FindingDecisionBody(BaseModel):
    decision: str


@router.get("/projects/{project_id}/compliance-matrix")
async def get_compliance_matrix(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
    entries = build_compliance_matrix(conn, project_id=project_id)
    return [
        {
            "requirement_id": e.requirement_id,
            "requirement_title": e.requirement_title,
            "category": e.category,
            "chapter_code": e.chapter_code,
            "coverage": e.coverage,
        }
        for e in entries
    ]


@router.post("/projects/{project_id}/compliance-check")
async def run_compliance_check(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _check_service.run(conn, project_id=project_id, created_by=user.display_name)


@router.get("/projects/{project_id}/compliance-check")
async def get_latest_compliance_check(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    latest = _check_service.latest(conn, project_id=project_id)
    return latest or {"project_id": str(project_id), "findings": [], "summary_json": {"finding_count": 0}}


@router.post("/compliance-findings/{finding_id}/decision")
async def update_compliance_finding_decision(
    finding_id: UUID,
    payload: FindingDecisionBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=finding_id,
        query=_FINDING_PROJECT_QUERY,
        not_found_detail="compliance finding not found",
        user=user,
    )
    try:
        row = _check_service.update_finding_decision(
            conn,
            finding_id=finding_id,
            decision=payload.decision,
            actor=user.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="compliance finding not found")
    return row
