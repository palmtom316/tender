"""API routes for export operations."""

from __future__ import annotations
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel
from pathlib import Path

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.delivery_package import build_delivery_package, get_delivery_package, list_delivery_packages
from tender_backend.services.export_service.docx_exporter import render_docx

router = APIRouter(tags=["exports"])
_DELIVERY_PACKAGE_PROJECT_QUERY = "SELECT project_id FROM bid_delivery_package WHERE id = %s"


class DeliveryPackageCreateBody(BaseModel):
    run_review: bool = True


@router.get("/projects/{project_id}/exports")
async def list_exports(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM export_record WHERE project_id = %s ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return rows


@router.post("/projects/{project_id}/exports")
async def create_export(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    output = render_docx(conn, project_id=project_id)
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            INSERT INTO export_record (id, project_id, status, template_name, export_key)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (uuid4(), project_id, "completed", "plain_docx", str(output)),
        ).fetchone()
    conn.commit()
    if row is None:
        raise HTTPException(status_code=500, detail="failed to create export record")
    return dict(row)


@router.get("/projects/{project_id}/export-gates")
async def check_export_gates(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Check all three export gates."""
    require_project_access(conn, project_id=project_id, user=user)
    from tender_backend.db.repositories.requirement_repo import RequirementRepository
    from tender_backend.services.review_service.review_engine import get_blocking_issues

    req_repo = RequirementRepository()
    unconfirmed_veto = req_repo.unconfirmed_veto_count(conn, project_id=project_id)
    blocking_issues = get_blocking_issues(conn, project_id=project_id)

    return {
        "project_id": str(project_id),
        "gates": {
            "veto_confirmed": unconfirmed_veto == 0,
            "unconfirmed_veto_count": unconfirmed_veto,
            "review_passed": len(blocking_issues) == 0,
            "blocking_issue_count": len(blocking_issues),
            "format_passed": True,  # Phase 1: format check is a warning
        },
        "can_export": unconfirmed_veto == 0 and len(blocking_issues) == 0,
    }


@router.post("/projects/{project_id}/delivery-package")
def create_delivery_package(
    project_id: UUID,
    _payload: DeliveryPackageCreateBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return build_delivery_package(conn, project_id=project_id, created_by=user.display_name)


@router.get("/projects/{project_id}/delivery-packages")
async def list_project_delivery_packages(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
    return list_delivery_packages(conn, project_id=project_id)


@router.get("/delivery-packages/{package_id}/download")
async def download_delivery_package(
    package_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    require_resource_project_access(
        conn,
        resource_id=package_id,
        query=_DELIVERY_PACKAGE_PROJECT_QUERY,
        not_found_detail="delivery package not found",
        user=user,
    )
    package = get_delivery_package(conn, package_id=package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="delivery package not found")
    path = Path(package["package_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="delivery package file not found")
    return FileResponse(path, media_type="application/zip", filename=package["package_name"])
