"""API routes for structured bid chart assets."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.project_access import require_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.chart_generation_service import ChartGenerationService, SUPPORTED_CHART_TYPES
from tender_backend.services.project_template_instance_service import ProjectTemplateInstanceService


router = APIRouter(tags=["charts"])
_service = ChartGenerationService()
_template_instances = ProjectTemplateInstanceService()


class ChartAssetBody(BaseModel):
    chart_type: str
    title: str
    spec_json: dict[str, Any]
    outline_node_id: UUID | None = None
    chapter_code: str | None = None


class ChartApprovalBody(BaseModel):
    approved_by: str | None = None


class ChartBulkApprovalBody(BaseModel):
    mode: str = "auto"
    approved_by: str | None = None


class ChartGenerateBody(BaseModel):
    chart_type: str
    title: str
    placeholder_key: str | None = None
    outline_node_id: UUID | None = None
    context: dict[str, Any] | None = None


def _template_revision_metadata(conn: Connection, *, project_id: UUID) -> dict[str, Any]:
    try:
        metadata = _template_instances.build_generation_inputs(conn, project_id=project_id).get("metadata") or {}
    except ValueError:
        return {}
    return {
        "template_instance_id": metadata.get("template_instance_id"),
        "template_revision_no": metadata.get("template_revision_no"),
    }


@router.get("/projects/{project_id}/chart-assets")
async def list_chart_assets(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
    return _service.list_by_project(conn, project_id=project_id)


@router.post("/projects/{project_id}/chart-assets")
async def create_chart_asset(
    project_id: UUID,
    payload: ChartAssetBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    template_metadata = _template_revision_metadata(conn, project_id=project_id)
    try:
        return _service.create_or_update(
            conn,
            project_id=project_id,
            chart_type=payload.chart_type,
            title=payload.title,
            spec_json=payload.spec_json,
            outline_node_id=payload.outline_node_id,
            chapter_code=payload.chapter_code,
            template_instance_id=UUID(str(template_metadata["template_instance_id"])) if template_metadata.get("template_instance_id") else None,
            template_revision_no=template_metadata.get("template_revision_no"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/chart-assets/generate")
async def generate_chart_asset(
    project_id: UUID,
    payload: ChartGenerateBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    spec = _service.generate_spec(
        chart_type=payload.chart_type,
        title=payload.title,
        placeholder_key=payload.placeholder_key,
        context=payload.context,
    )
    template_metadata = _template_revision_metadata(conn, project_id=project_id)
    try:
        return _service.create_or_update(
            conn,
            project_id=project_id,
            chart_type=payload.chart_type,
            title=payload.title,
            spec_json=spec,
            outline_node_id=payload.outline_node_id,
            template_instance_id=UUID(str(template_metadata["template_instance_id"])) if template_metadata.get("template_instance_id") else None,
            template_revision_no=template_metadata.get("template_revision_no"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/chart-assets/{asset_id}/approve")
async def approve_chart_asset(
    asset_id: UUID,
    payload: ChartApprovalBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    from tender_backend.core.project_access import require_resource_project_access

    require_resource_project_access(
        conn,
        resource_id=asset_id,
        query="SELECT project_id FROM chart_asset WHERE id = %s",
        not_found_detail="chart asset not found",
        user=user,
    )
    try:
        return _service.approve(
            conn,
            asset_id=asset_id,
            approved_by=(payload.approved_by if payload and payload.approved_by else user.display_name),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/chart-assets/supported-types")
async def list_supported_chart_types() -> dict:
    return {"types": sorted(SUPPORTED_CHART_TYPES)}


@router.post("/projects/{project_id}/chart-assets/bulk-approve")
async def bulk_approve_chart_assets(
    project_id: UUID,
    payload: ChartBulkApprovalBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    body = payload or ChartBulkApprovalBody()
    with conn.cursor() as cur:
        row = cur.execute(
            "SELECT metadata_json FROM project WHERE id = %s",
            (project_id,),
        ).fetchone()
    metadata = (row[0] if row else None) or {}
    is_blind_bid = bool(metadata.get("is_blind_bid"))
    try:
        return _service.bulk_approve(
            conn,
            project_id=project_id,
            mode=body.mode,
            approved_by=(body.approved_by or user.display_name or "system"),
            is_blind_bid=is_blind_bid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
