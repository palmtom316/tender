"""API routes for export operations."""

from __future__ import annotations
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel
from pathlib import Path

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.external_attachment_repo import ExternalAttachmentRepository
from tender_backend.services.delivery_package import build_delivery_package, get_delivery_package, list_delivery_packages
from tender_backend.services.submission_checklist_service import SubmissionChecklistService
from tender_backend.services.export_gate_service import build_export_gate_state
from tender_backend.services.export_service.docx_exporter import (
    EXPORT_MODES,
    EXPORT_MODE_MULTI_DOC_ZIP,
    EXPORT_MODE_MULTI_DOCX_ZIP,
    EXPORT_MODE_SINGLE_DOCX,
    inspect_rendered_docx_evidence,
    render_export,
)

router = APIRouter(tags=["exports"])
_attachment_repo = ExternalAttachmentRepository()
_checklist_service = SubmissionChecklistService()
_DELIVERY_PACKAGE_PROJECT_QUERY = "SELECT project_id FROM bid_delivery_package WHERE id = %s"
_EXPORT_RECORD_PROJECT_QUERY = "SELECT project_id FROM export_record WHERE id = %s"

ExportMode = Literal["single_docx", "multi_docx_zip", "multi_doc_zip"]

_MODE_TO_TEMPLATE_NAME = {
    EXPORT_MODE_SINGLE_DOCX: "plain_docx",
    EXPORT_MODE_MULTI_DOCX_ZIP: "chapter_docx_zip",
    EXPORT_MODE_MULTI_DOC_ZIP: "chapter_doc_zip",
}

_MODE_TO_DOWNLOAD_SUFFIX = {
    EXPORT_MODE_SINGLE_DOCX: (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    EXPORT_MODE_MULTI_DOCX_ZIP: (".zip", "application/zip"),
    EXPORT_MODE_MULTI_DOC_ZIP: (".zip", "application/zip"),
}

class CreateExportBody(BaseModel):
    mode: ExportMode = EXPORT_MODE_SINGLE_DOCX


class DeliveryPackageCreateBody(BaseModel):
    run_review: bool = True


class ExternalAttachmentCreateBody(BaseModel):
    filename: str
    volume_type: str = "pricing"
    attachment_type: str = "external_pricing"
    file_path: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    metadata_json: dict | None = None


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
    body: CreateExportBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    mode = (body.mode if body else EXPORT_MODE_SINGLE_DOCX)
    if mode not in EXPORT_MODES:
        raise HTTPException(status_code=400, detail=f"unsupported export mode: {mode}")
    gate_state = build_export_gate_state(conn, project_id=project_id)
    if not gate_state.get("can_export"):
        raise HTTPException(status_code=409, detail=f"export gates block export: {gate_state.get('gates')}")
    try:
        output = render_export(conn, project_id=project_id, mode=mode)
        output_path = Path(output)
        render_evidence = (
            inspect_rendered_docx_evidence(output_path)
            if output_path.suffix == ".docx"
            else {"path": str(output_path), "page_count": {"status": "unchecked", "actual_pages": None}}
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    template_name = _MODE_TO_TEMPLATE_NAME.get(mode, mode)
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            INSERT INTO export_record (id, project_id, status, template_name, export_key, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (uuid4(), project_id, "completed", template_name, str(output), Jsonb({"render_evidence": render_evidence})),
        ).fetchone()
    conn.commit()
    if row is None:
        raise HTTPException(status_code=500, detail="failed to create export record")
    result = dict(row)
    result["mode"] = mode
    return result


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    require_resource_project_access(
        conn,
        resource_id=export_id,
        query=_EXPORT_RECORD_PROJECT_QUERY,
        not_found_detail="export record not found",
        user=user,
    )
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT * FROM export_record WHERE id = %s",
            (export_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="export record not found")
    export_key = row.get("export_key")
    if not export_key:
        raise HTTPException(status_code=404, detail="export file path missing")
    path = Path(export_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="export file not found")
    suffix, media_type = _MODE_TO_DOWNLOAD_SUFFIX.get(
        _template_name_to_mode(row.get("template_name")),
        (path.suffix, "application/octet-stream"),
    )
    filename = path.name if path.suffix == suffix else f"{path.stem}{suffix}"
    return FileResponse(path, media_type=media_type, filename=filename)


def _template_name_to_mode(template_name: str | None) -> str:
    if not template_name:
        return EXPORT_MODE_SINGLE_DOCX
    for mode, alias in _MODE_TO_TEMPLATE_NAME.items():
        if alias == template_name:
            return mode
    return EXPORT_MODE_SINGLE_DOCX


@router.get("/projects/{project_id}/export-gates")
async def check_export_gates(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Check all three export gates."""
    require_project_access(conn, project_id=project_id, user=user)
    return build_export_gate_state(conn, project_id=project_id)


@router.post("/projects/{project_id}/external-attachments")
async def create_external_attachment(
    project_id: UUID,
    payload: ExternalAttachmentCreateBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _attachment_repo.create(
        conn,
        project_id=project_id,
        filename=payload.filename,
        volume_type=payload.volume_type,
        attachment_type=payload.attachment_type,
        file_path=payload.file_path,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        metadata_json=payload.metadata_json,
    )


@router.get("/projects/{project_id}/external-attachments")
async def list_external_attachments(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
    return _attachment_repo.list_by_project(conn, project_id=project_id)


@router.get("/projects/{project_id}/submission-checklist")
async def get_submission_checklist(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _checklist_service.build(conn, project_id=project_id)


@router.post("/projects/{project_id}/delivery-package")
def create_delivery_package(
    project_id: UUID,
    _payload: DeliveryPackageCreateBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        return build_delivery_package(conn, project_id=project_id, created_by=user.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
