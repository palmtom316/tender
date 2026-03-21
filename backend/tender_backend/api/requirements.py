"""API routes for project requirements and human confirmation."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.security import CurrentUser, Role, get_current_user, require_role
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.requirement_repo import RequirementRepository

router = APIRouter(tags=["requirements"])
_repo = RequirementRepository()


class ConfirmBody(BaseModel):
    confirmed: bool = True


@router.get("/projects/{project_id}/requirements")
async def list_requirements(
    project_id: UUID,
    category: str | None = None,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return _repo.list_by_project(conn, project_id=project_id, category=category)


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
