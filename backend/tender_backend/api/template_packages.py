from __future__ import annotations

import re
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.config import Settings, get_settings
from tender_backend.core.path_safety import parse_root_list
from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository
from tender_backend.services.template_service.package_importer import (
    import_template_package_from_directory,
)
from tender_backend.services.template_selection_service import TemplateSelectionService
from tender_backend.core.project_access import require_project_access
from tender_backend.core.security import CurrentUser


router = APIRouter(tags=["template-packages"], dependencies=[Depends(get_current_user)])

_repo = BidTemplatePackageRepository()
_selection = TemplateSelectionService(template_repo=_repo)
_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PACKAGE_KEY_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class TemplatePackageImportBody(BaseModel):
    source_dir: str = Field(min_length=1)
    package_key: str | None = None
    display_name: str | None = None
    package_type: str | None = None
    category_code: str | None = None


class TemplatePackageCategoryOut(BaseModel):
    code: str
    display_name: str
    description: str | None
    sort_order: int
    enabled: bool
    metadata_json: dict


class TemplateItemOut(BaseModel):
    id: UUID
    item_code: str | None
    item_name: str
    filename: str
    relative_path: str
    source_kind: str
    item_type: str
    render_mode: str
    is_required: bool
    sort_order: int


class TemplatePackageOut(BaseModel):
    id: UUID
    package_key: str
    display_name: str
    package_type: str
    category_code: str | None
    source_root: str
    item_count: int


class TemplatePackageDetailOut(TemplatePackageOut):
    items: list[TemplateItemOut]


class TemplateSelectionConfirmBody(BaseModel):
    package_id: UUID


def _sanitize_package_key_part(value: str) -> str:
    cleaned = _PACKAGE_KEY_SAFE_RE.sub("-", value).strip("-._").lower()
    return cleaned or "template"


async def _save_uploaded_template_docx(file: UploadFile, settings: Settings) -> str:
    roots = parse_root_list(settings.template_import_roots)
    if not roots:
        raise HTTPException(status_code=400, detail="template import roots are not configured")
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="template file must be a DOCX file")
    if file.content_type and file.content_type not in {_DOCX_CONTENT_TYPE, "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="template file content type is not allowed")

    content = await file.read()
    if not content.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=400, detail="template file is not a valid DOCX archive")

    upload_dir = roots[0] / "uploaded_template_packages"
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix_dir = upload_dir / str(uuid4())
    suffix_dir.mkdir()
    template_path = suffix_dir / "template.docx"
    template_path.write_bytes(content)
    return str(template_path)


def _package_out(conn: Connection, package_id: UUID) -> TemplatePackageDetailOut | None:
    package = _repo.get_by_id(conn, package_id=package_id)
    if package is None:
        return None
    items = _repo.list_items(conn, package_id=package.id)
    return TemplatePackageDetailOut(
        id=package.id,
        package_key=package.package_key,
        display_name=package.display_name,
        package_type=package.package_type,
        category_code=package.category_code,
        source_root=package.source_root,
        item_count=len(items),
        items=[
            TemplateItemOut(
                id=item.id,
                item_code=item.item_code,
                item_name=item.item_name,
                filename=item.filename,
                relative_path=item.relative_path,
                source_kind=item.source_kind,
                item_type=item.item_type,
                render_mode=item.render_mode,
                is_required=item.is_required,
                sort_order=item.sort_order,
            )
            for item in items
        ],
    )


@router.get("/template-package-categories", response_model=list[TemplatePackageCategoryOut])
async def list_template_package_categories(conn: Connection = Depends(get_db_conn)) -> list[TemplatePackageCategoryOut]:
    return [
        TemplatePackageCategoryOut(
            code=row.code,
            display_name=row.display_name,
            description=row.description,
            sort_order=row.sort_order,
            enabled=row.enabled,
            metadata_json=row.metadata_json,
        )
        for row in _repo.list_categories(conn)
    ]


@router.get("/template-packages", response_model=list[TemplatePackageOut])
async def list_template_packages(
    category_code: str | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[TemplatePackageOut]:
    packages = _repo.list_all(conn)
    if category_code:
        packages = [package for package in packages if package.category_code == category_code]
    items_by_package = _repo.count_items_by_package(conn, package_ids=[package.id for package in packages])
    return [
        TemplatePackageOut(
            id=package.id,
            package_key=package.package_key,
            display_name=package.display_name,
            package_type=package.package_type,
            category_code=package.category_code,
            source_root=package.source_root,
            item_count=items_by_package.get(package.id, 0),
        )
        for package in packages
    ]


@router.get("/template-packages/{package_id}", response_model=TemplatePackageDetailOut)
async def get_template_package(package_id: UUID, conn: Connection = Depends(get_db_conn)) -> TemplatePackageDetailOut:
    result = _package_out(conn, package_id)
    if result is None:
        raise HTTPException(status_code=404, detail="template package not found")
    return result


@router.get("/projects/{project_id}/template-selection")
async def preview_project_template_selection(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        return _selection.preview(conn, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/template-selection")
async def confirm_project_template_selection(
    project_id: UUID,
    payload: TemplateSelectionConfirmBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        return _selection.confirm(conn, project_id=project_id, package_id=payload.package_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/template-packages/import", response_model=TemplatePackageDetailOut)
async def import_template_package(
    payload: TemplatePackageImportBody,
    conn: Connection = Depends(get_db_conn),
) -> TemplatePackageDetailOut:
    try:
        imported = import_template_package_from_directory(
            conn,
            source_dir=payload.source_dir.strip(),
            package_key=(payload.package_key or "").strip() or None,
            display_name=(payload.display_name or "").strip() or None,
            package_type=(payload.package_type or "").strip() or None,
            category_code=(payload.category_code or "").strip() or None,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = _package_out(conn, UUID(imported.package_id))
    assert result is not None
    return result


@router.post("/template-packages/upload", response_model=TemplatePackageDetailOut, status_code=201)
async def upload_template_package(
    project_type: str = Form(...),
    template_kind: str = Form(...),
    display_name: str | None = Form(None),
    category_code: str | None = Form(None),
    file: UploadFile = File(...),
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
) -> TemplatePackageDetailOut:
    normalized_project_type = project_type.strip()
    normalized_kind = template_kind.strip()
    if not normalized_project_type:
        raise HTTPException(status_code=400, detail="project_type is required")
    if normalized_kind not in {"business", "technical"}:
        raise HTTPException(status_code=400, detail="template_kind must be business or technical")

    source_path = await _save_uploaded_template_docx(file, settings)
    resolved_display_name = (display_name or "").strip() or (
        f"{normalized_project_type}{'商务标模板' if normalized_kind == 'business' else '技术标模板'}"
    )
    package_key = "-".join(
        [
            _sanitize_package_key_part(normalized_project_type),
            normalized_kind,
            "single-docx",
        ]
    )
    try:
        imported = import_template_package_from_directory(
            conn,
            source_dir=source_path,
            package_key=package_key,
            display_name=resolved_display_name,
            package_type=normalized_kind,
            category_code=(category_code or "").strip() or None,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = _package_out(conn, UUID(imported.package_id))
    assert result is not None
    return result
