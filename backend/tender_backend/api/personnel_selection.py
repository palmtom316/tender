from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.project_personnel_selection_repo import ProjectPersonnelSelectionRepository
from tender_backend.services.export_service.personnel_table_renderer import PersonnelTableRenderer


router = APIRouter(tags=["personnel"])

_repo = ProjectPersonnelSelectionRepository()
_renderer = PersonnelTableRenderer()
_SELECTION_PROJECT_QUERY = "SELECT project_id FROM project_personnel_selection WHERE id = %s"


class PersonnelSelectionCreate(BaseModel):
    person_id: UUID


class PersonnelSelectionUpdate(BaseModel):
    intended_role: str | None = None
    display_order: int | None = Field(default=None, ge=0)


def _person_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": str(row["id"]),
        "library_company_id": str(row["library_company_id"]) if row.get("library_company_id") else None,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "profile_json": dict(row.get("profile_json") or {}),
    }


def _selection_out(row) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "person_id": str(row.person_id),
        "intended_role": row.intended_role,
        "snapshot_json": row.snapshot_json,
        "display_order": row.display_order,
        "confirmed": row.confirmed,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/projects/{project_id}/personnel/people")
async def list_project_personnel_candidates(
    project_id: UUID,
    library_company_id: UUID | None = Query(None),
    q: str | None = Query(None),
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_project_access(conn, project_id=project_id, user=user)
    rows = _repo.list_people(conn, library_company_id=library_company_id, q=q)
    return [_person_out(row) for row in rows]


@router.get("/projects/{project_id}/personnel/selections")
async def list_project_personnel_selections(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_project_access(conn, project_id=project_id, user=user)
    return [_selection_out(row) for row in _repo.list_selections(conn, project_id=project_id)]


@router.post("/projects/{project_id}/personnel/selections", status_code=201)
async def create_project_personnel_selection(
    project_id: UUID,
    payload: PersonnelSelectionCreate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        row = _repo.create_selection(conn, project_id=project_id, person_id=payload.person_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _selection_out(row)


@router.put("/projects/{project_id}/personnel/selections/{selection_id}")
async def update_project_personnel_selection(
    project_id: UUID,
    selection_id: UUID,
    payload: PersonnelSelectionUpdate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    resource_project_id = require_resource_project_access(
        conn,
        resource_id=selection_id,
        query=_SELECTION_PROJECT_QUERY,
        not_found_detail="personnel selection not found",
        user=user,
    )
    if resource_project_id != project_id:
        raise HTTPException(status_code=404, detail="personnel selection not found")
    row = _repo.update_selection(conn, selection_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="personnel selection not found")
    return _selection_out(row)


@router.delete("/projects/{project_id}/personnel/selections/{selection_id}")
async def delete_project_personnel_selection(
    project_id: UUID,
    selection_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, bool]:
    resource_project_id = require_resource_project_access(
        conn,
        resource_id=selection_id,
        query=_SELECTION_PROJECT_QUERY,
        not_found_detail="personnel selection not found",
        user=user,
    )
    if resource_project_id != project_id:
        raise HTTPException(status_code=404, detail="personnel selection not found")
    deleted = _repo.delete_selection(conn, selection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="personnel selection not found")
    return {"deleted": True}


@router.post("/projects/{project_id}/personnel/selections/confirm")
async def confirm_project_personnel_selections(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_project_access(conn, project_id=project_id, user=user)
    return [_selection_out(row) for row in _repo.confirm_project_selections(conn, project_id=project_id)]


@router.get("/projects/{project_id}/personnel/preview")
async def preview_project_personnel_table(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, str]]:
    require_project_access(conn, project_id=project_id, user=user)
    return _renderer.render_personnel_preview(conn, project_id=project_id)
