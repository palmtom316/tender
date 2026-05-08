from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.project_equipment_selection_repo import ProjectEquipmentSelectionRepository
from tender_backend.services.export_service.equipment_table_renderer import EquipmentTableRenderer
import io


router = APIRouter(tags=["equipment"])

_repo = ProjectEquipmentSelectionRepository()
_renderer = EquipmentTableRenderer()
_SELECTION_PROJECT_QUERY = "SELECT project_id FROM project_equipment_selection WHERE id = %s"


class EquipmentSelectionCreate(BaseModel):
    asset_id: UUID


class EquipmentSelectionUpdate(BaseModel):
    intended_role: str | None = None
    display_order: int | None = Field(default=None, ge=0)


@router.get("/projects/{project_id}/equipment/assets")
async def list_project_equipment_assets(
    project_id: UUID,
    asset_type: str | None = Query(None),
    q: str | None = Query(None),
    status: str | None = Query(None),
    valid_only: bool = Query(False),
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_project_access(conn, project_id=project_id, user=user)
    rows = _repo.list_assets(
        conn,
        asset_type=asset_type,
        q=q,
        status=status,
        valid_only=valid_only,
    )
    return [
        {
            **dict(row),
            "id": str(row["id"]),
            "library_company_id": str(row["library_company_id"]),
            "quantity": str(row["quantity"]),
            "acquired_at": row["acquired_at"].isoformat() if row["acquired_at"] else None,
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "extras": dict(row["extras"] or {}),
        }
        for row in rows
    ]


@router.get("/projects/{project_id}/equipment/selections")
async def list_project_equipment_selections(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_project_access(conn, project_id=project_id, user=user)
    rows = _repo.list_selections(conn, project_id=project_id)
    return [
        {
            "id": str(row.id),
            "project_id": str(row.project_id),
            "asset_id": str(row.asset_id),
            "asset_type": row.asset_type,
            "intended_role": row.intended_role,
            "snapshot_json": row.snapshot_json,
            "display_order": row.display_order,
            "confirmed": row.confirmed,
            "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/projects/{project_id}/equipment/selections", status_code=201)
async def create_project_equipment_selection(
    project_id: UUID,
    payload: EquipmentSelectionCreate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        row = _repo.create_selection(conn, project_id=project_id, asset_id=payload.asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "asset_id": str(row.asset_id),
        "asset_type": row.asset_type,
        "intended_role": row.intended_role,
        "snapshot_json": row.snapshot_json,
        "display_order": row.display_order,
        "confirmed": row.confirmed,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.put("/projects/{project_id}/equipment/selections/{selection_id}")
async def update_project_equipment_selection(
    project_id: UUID,
    selection_id: UUID,
    payload: EquipmentSelectionUpdate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    resource_project_id = require_resource_project_access(
        conn,
        resource_id=selection_id,
        query=_SELECTION_PROJECT_QUERY,
        not_found_detail="equipment selection not found",
        user=user,
    )
    if resource_project_id != project_id:
        raise HTTPException(status_code=404, detail="equipment selection not found")
    row = _repo.update_selection(conn, selection_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="equipment selection not found")
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "asset_id": str(row.asset_id),
        "asset_type": row.asset_type,
        "intended_role": row.intended_role,
        "snapshot_json": row.snapshot_json,
        "display_order": row.display_order,
        "confirmed": row.confirmed,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.delete("/projects/{project_id}/equipment/selections/{selection_id}")
async def delete_project_equipment_selection(
    project_id: UUID,
    selection_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, bool]:
    resource_project_id = require_resource_project_access(
        conn,
        resource_id=selection_id,
        query=_SELECTION_PROJECT_QUERY,
        not_found_detail="equipment selection not found",
        user=user,
    )
    if resource_project_id != project_id:
        raise HTTPException(status_code=404, detail="equipment selection not found")
    deleted = _repo.delete_selection(conn, selection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="equipment selection not found")
    return {"deleted": True}


@router.post("/projects/{project_id}/equipment/selections/confirm")
async def confirm_project_equipment_selections(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_project_access(conn, project_id=project_id, user=user)
    rows = _repo.confirm_project_selections(conn, project_id=project_id)
    return [
        {
            "id": str(row.id),
            "project_id": str(row.project_id),
            "asset_id": str(row.asset_id),
            "asset_type": row.asset_type,
            "intended_role": row.intended_role,
            "snapshot_json": row.snapshot_json,
            "display_order": row.display_order,
            "confirmed": row.confirmed,
            "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/projects/{project_id}/equipment/preview")
async def preview_project_equipment_tables(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, list[dict[str, str]]]:
    require_project_access(conn, project_id=project_id, user=user)
    return _renderer.render_equipment_preview(conn, project_id=project_id)


@router.get("/projects/{project_id}/equipment/attachment-xlsx")
async def download_project_equipment_xlsx(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    require_project_access(conn, project_id=project_id, user=user)
    data = _renderer.render_attachment_xlsx(conn, project_id=project_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="equipment-table-{project_id}.xlsx"'},
    )
