from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg import Connection, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.bid_template_binding_repo import BidTemplateBindingRepository
from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository
from tender_backend.services.template_service.context_preview import (
    build_item_render_context,
    build_item_field_mapping_suggestions,
    build_package_context_preview,
    build_package_render_context,
    validate_field_mapping_mode,
    validate_field_mappings,
    validate_selection_mode,
    validate_source_type,
)
from tender_backend.services.template_service.docx_renderer import render_template_item_docx
from tender_backend.services.template_service.package_renderer import (
    preflight_template_package_bundle,
    render_template_package_bundle,
)


router = APIRouter(tags=["template-bindings"], dependencies=[Depends(get_current_user)])

_bindings = BidTemplateBindingRepository()
_packages = BidTemplatePackageRepository()


class BindingRuleBase(BaseModel):
    binding_name: str = Field(min_length=1)
    source_type: str
    selection_mode: str = "all"
    source_filters: dict[str, Any] = Field(default_factory=dict)
    field_mappings: list[dict[str, Any]] = Field(default_factory=list)
    field_mapping_mode: str = "augment"
    output_key: str = Field(min_length=1)
    required: bool = True
    sort_order: int = 0


class BindingRuleCreate(BindingRuleBase):
    pass


class BindingRuleUpdate(BaseModel):
    binding_name: str | None = None
    source_type: str | None = None
    selection_mode: str | None = None
    source_filters: dict[str, Any] | None = None
    field_mappings: list[dict[str, Any]] | None = None
    field_mapping_mode: str | None = None
    output_key: str | None = None
    required: bool | None = None
    sort_order: int | None = None


class BindingRuleOut(BindingRuleBase):
    id: UUID
    template_item_id: UUID
    created_at: str
    updated_at: str


class RenderBundleBody(BaseModel):
    include_zip: bool = False
    project_id: UUID | None = None


class RenderItemBody(BaseModel):
    project_id: UUID | None = None


def _persist_template_render_status(conn: Connection, *, project_id: UUID, result: dict[str, Any]) -> None:
    failed_required_items = [
        str(item.get("filename") or item.get("relative_path") or item.get("item_code") or "unknown")
        for item in result.get("items") or []
        if item.get("required") and item.get("status") == "failed"
    ]
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT metadata_json FROM project WHERE id = %s", (project_id,)).fetchone()
        metadata = dict((row or {}).get("metadata_json") or {})
        metadata["template_render_status"] = {
            "required_failed_count": int(result.get("required_failed_count") or 0),
            "failed_count": int(result.get("failed_count") or 0),
            "rendered_count": int(result.get("rendered_count") or 0),
            "total_item_count": int(result.get("total_item_count") or 0),
            "failed_required_items": failed_required_items,
        }
        cur.execute(
            "UPDATE project SET metadata_json = %s WHERE id = %s",
            (Jsonb(metadata), project_id),
        )
    conn.commit()


def _binding_out(row) -> BindingRuleOut:
    return BindingRuleOut(
        id=row.id,
        template_item_id=row.template_item_id,
        binding_name=row.binding_name,
        source_type=row.source_type,
        selection_mode=row.selection_mode,
        source_filters=row.source_filters,
        field_mappings=row.field_mappings,
        field_mapping_mode=row.field_mapping_mode,
        output_key=row.output_key,
        required=row.required,
        sort_order=row.sort_order,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _validate_payload(payload: BindingRuleBase | BindingRuleUpdate) -> None:
    raw = payload.model_dump(exclude_unset=True)
    if "source_type" in raw and raw["source_type"] is not None:
        validate_source_type(raw["source_type"])
    if "selection_mode" in raw and raw["selection_mode"] is not None:
        validate_selection_mode(raw["selection_mode"])
    if "field_mapping_mode" in raw and raw["field_mapping_mode"] is not None:
        validate_field_mapping_mode(raw["field_mapping_mode"])
    if "field_mappings" in raw and raw["field_mappings"] is not None:
        validate_field_mappings(raw["field_mappings"])


@router.get("/template-items/{template_item_id}/bindings", response_model=list[BindingRuleOut])
async def list_item_bindings(template_item_id: UUID, conn: Connection = Depends(get_db_conn)) -> list[BindingRuleOut]:
    item = _packages.get_item_by_id(conn, item_id=template_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="template item not found")
    return [_binding_out(row) for row in _bindings.list_by_item(conn, template_item_id=template_item_id)]


@router.post("/template-items/{template_item_id}/bindings", response_model=BindingRuleOut, status_code=201)
async def create_item_binding(
    template_item_id: UUID,
    payload: BindingRuleCreate,
    conn: Connection = Depends(get_db_conn),
) -> BindingRuleOut:
    item = _packages.get_item_by_id(conn, item_id=template_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="template item not found")
    _validate_payload(payload)
    try:
        row = _bindings.create(conn, template_item_id=template_item_id, **payload.model_dump())
    except errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="binding name already exists for template item") from exc
    return _binding_out(row)


@router.put("/template-bindings/{rule_id}", response_model=BindingRuleOut)
async def update_binding_rule(
    rule_id: UUID,
    payload: BindingRuleUpdate,
    conn: Connection = Depends(get_db_conn),
) -> BindingRuleOut:
    _validate_payload(payload)
    try:
        row = _bindings.update(conn, rule_id=rule_id, **payload.model_dump(exclude_unset=True))
    except errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="binding name already exists for template item") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="binding rule not found")
    return _binding_out(row)


@router.delete("/template-bindings/{rule_id}")
async def delete_binding_rule(rule_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    deleted = _bindings.delete(conn, rule_id=rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="binding rule not found")
    return {"deleted": True}


@router.get("/template-packages/{package_id}/context-preview")
async def get_package_context_preview(package_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, Any]:
    try:
        return build_package_context_preview(conn, package_id=package_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/template-items/{template_item_id}/render-context")
async def get_item_render_context(
    template_item_id: UUID,
    project_id: UUID | None = None,
    conn: Connection = Depends(get_db_conn),
) -> dict[str, Any]:
    try:
        return build_item_render_context(conn, item_id=template_item_id, project_id=project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/template-items/{template_item_id}/field-mapping-suggestions")
async def get_item_field_mapping_suggestions(template_item_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, Any]:
    try:
        return build_item_field_mapping_suggestions(conn, item_id=template_item_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/template-packages/{package_id}/render-context")
async def get_package_render_context(
    package_id: UUID,
    project_id: UUID | None = None,
    conn: Connection = Depends(get_db_conn),
) -> dict[str, Any]:
    try:
        return build_package_render_context(conn, package_id=package_id, project_id=project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/template-packages/{package_id}/render-preflight")
async def get_package_render_preflight(package_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, Any]:
    try:
        return preflight_template_package_bundle(conn, package_id=package_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/template-items/{template_item_id}/render-docx")
async def render_template_item_docx_endpoint(
    template_item_id: UUID,
    payload: RenderItemBody | None = None,
    conn: Connection = Depends(get_db_conn),
) -> dict[str, object]:
    try:
        return render_template_item_docx(
            conn,
            item_id=template_item_id,
            project_id=payload.project_id if payload else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/template-packages/{package_id}/render-bundle")
async def render_template_package_bundle_endpoint(
    package_id: UUID,
    payload: RenderBundleBody,
    conn: Connection = Depends(get_db_conn),
) -> dict[str, object]:
    try:
        result = render_template_package_bundle(
            conn,
            package_id=package_id,
            include_zip=payload.include_zip,
            project_id=payload.project_id,
        )
        if payload.project_id is not None:
            _persist_template_render_status(conn, project_id=payload.project_id, result=result)
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
