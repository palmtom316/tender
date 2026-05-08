from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.config import Settings, get_settings
from tender_backend.core.path_safety import ensure_path_within_root
from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.master_data_repo import MasterDataRepository


router = APIRouter(tags=["master-data"], dependencies=[Depends(get_current_user)])

_repo = MasterDataRepository()
_EVIDENCE_OWNER_TYPES = {
    "library_company",
    "company_asset",
    "company_profile",
    "person_profile",
    "project_performance",
    "qualification_certificate",
    "financial_statement",
}
_ALLOWED_UPLOAD_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class EvidenceAssetOut(BaseModel):
    id: UUID
    library_company_id: UUID | None = None
    owner_type: str
    owner_id: UUID | None = None
    asset_name: str
    asset_domain: str = "generic"
    asset_category: str = "supporting_document"
    asset_type: str = "supporting_document"
    file_name: str
    media_type: str | None = None
    issuer_name: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    created_at: str
    updated_at: str


class EvidenceAssetBase(BaseModel):
    library_company_id: UUID | None = None
    owner_type: str = Field(min_length=1)
    owner_id: UUID | None = None
    asset_name: str = Field(min_length=1)
    asset_domain: str = "generic"
    asset_category: str = "supporting_document"
    asset_type: str = "supporting_document"
    file_name: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    media_type: str | None = None
    issuer_name: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class EvidenceAssetCreate(EvidenceAssetBase):
    pass


class EvidenceAssetUpdate(BaseModel):
    library_company_id: UUID | None = None
    owner_type: str | None = None
    owner_id: UUID | None = None
    asset_name: str | None = None
    asset_domain: str | None = None
    asset_category: str | None = None
    asset_type: str | None = None
    file_name: str | None = None
    file_path: str | None = None
    media_type: str | None = None
    issuer_name: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    metadata_json: dict[str, Any] | None = None
    sort_order: int | None = None


def _validate_evidence_owner_type(value: str) -> str:
    if value not in _EVIDENCE_OWNER_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported evidence owner_type: {value}")
    return value


def _parse_json_text(raw: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{label} must be a JSON object")
    return value


def _magic_media_type(content: bytes) -> str | None:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"BM"):
        return "image/bmp"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return None


def _validate_managed_asset_path(file_path: str, *, settings: Settings) -> str:
    try:
        resolved = ensure_path_within_root(file_path, settings.evidence_upload_dir, label="file_path")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"file_path does not exist: {resolved}")
    return str(resolved)


def _validate_uploaded_file(file: UploadFile, content: bytes, *, settings: Settings) -> tuple[str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    expected_media_type = _ALLOWED_UPLOAD_TYPES.get(suffix)
    if expected_media_type is None:
        raise HTTPException(status_code=400, detail="unsupported upload file type")
    if len(content) > settings.evidence_upload_max_bytes:
        raise HTTPException(status_code=413, detail="uploaded file exceeds size limit")
    detected_media_type = _magic_media_type(content)
    if detected_media_type is None or detected_media_type != expected_media_type:
        raise HTTPException(status_code=400, detail="uploaded file content does not match its extension")
    claimed_media_type = (file.content_type or "").lower()
    if claimed_media_type and claimed_media_type not in {expected_media_type, "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="uploaded file content type is not allowed")
    return suffix, expected_media_type


def _evidence_asset_out(row) -> EvidenceAssetOut:
    return EvidenceAssetOut(
        id=row.id,
        library_company_id=row.library_company_id,
        owner_type=row.owner_type,
        owner_id=row.owner_id,
        asset_name=row.asset_name,
        asset_domain=row.asset_domain,
        asset_category=row.asset_category,
        asset_type=row.asset_type,
        file_name=row.file_name,
        media_type=row.media_type,
        issuer_name=row.issuer_name,
        issued_on=row.issued_on,
        expires_on=row.expires_on,
        metadata_json=row.metadata_json,
        sort_order=row.sort_order,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/master-data/evidence-assets", response_model=list[EvidenceAssetOut])
async def list_evidence_assets(
    library_company_id: UUID | None = Query(None),
    asset_domain: str | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[EvidenceAssetOut]:
    return [
        _evidence_asset_out(row)
        for row in _repo.list_evidence_assets(
            conn,
            library_company_id=library_company_id,
            asset_domain=asset_domain,
        )
    ]


@router.post("/master-data/evidence-assets", response_model=EvidenceAssetOut, status_code=201)
async def create_evidence_asset(
    payload: EvidenceAssetCreate,
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
) -> EvidenceAssetOut:
    _validate_evidence_owner_type(payload.owner_type)
    body = payload.model_dump()
    body["file_path"] = _validate_managed_asset_path(body["file_path"], settings=settings)
    return _evidence_asset_out(_repo.create_evidence_asset(conn, **body))


@router.post("/master-data/evidence-assets/upload", response_model=EvidenceAssetOut, status_code=201)
async def upload_evidence_asset(
    library_company_id: UUID | None = Form(None),
    owner_type: str = Form(...),
    owner_id: UUID | None = Form(None),
    asset_name: str = Form(...),
    asset_domain: str = Form("generic"),
    asset_category: str = Form("supporting_document"),
    asset_type: str = Form("supporting_document"),
    issuer_name: str | None = Form(None),
    issued_on: date | None = Form(None),
    expires_on: date | None = Form(None),
    sort_order: int = Form(0),
    metadata_json: str = Form("{}"),
    file: UploadFile = File(...),
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
) -> EvidenceAssetOut:
    _validate_evidence_owner_type(owner_type)
    payload = _parse_json_text(metadata_json, label="metadata_json")
    content = await file.read()
    suffix, media_type = _validate_uploaded_file(file, content, settings=settings)
    local_name = f"{uuid4()}{suffix}"
    settings.evidence_upload_dir.mkdir(parents=True, exist_ok=True)
    local_path = settings.evidence_upload_dir / local_name
    local_path.write_bytes(content)
    row = _repo.create_evidence_asset(
        conn,
        library_company_id=library_company_id,
        owner_type=owner_type,
        owner_id=owner_id,
        asset_name=asset_name,
        asset_domain=asset_domain,
        asset_category=asset_category,
        asset_type=asset_type,
        file_name=file.filename or local_name,
        file_path=str(local_path),
        media_type=media_type,
        issuer_name=issuer_name,
        issued_on=issued_on,
        expires_on=expires_on,
        metadata_json=payload,
        sort_order=sort_order,
    )
    return _evidence_asset_out(row)


@router.post("/master-data/evidence-assets/{record_id}/replace-file", response_model=EvidenceAssetOut)
async def replace_evidence_asset_file(
    record_id: UUID,
    file: UploadFile = File(...),
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
) -> EvidenceAssetOut:
    row = _repo.get_evidence_asset(conn, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="evidence asset not found")
    content = await file.read()
    suffix, media_type = _validate_uploaded_file(file, content, settings=settings)
    local_name = f"{uuid4()}{suffix}"
    settings.evidence_upload_dir.mkdir(parents=True, exist_ok=True)
    local_path = settings.evidence_upload_dir / local_name
    local_path.write_bytes(content)
    updated = _repo.update_evidence_asset(
        conn,
        record_id,
        file_name=file.filename or local_name,
        file_path=str(local_path),
        media_type=media_type,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="evidence asset not found")
    return _evidence_asset_out(updated)


@router.put("/master-data/evidence-assets/{record_id}", response_model=EvidenceAssetOut)
async def update_evidence_asset(
    record_id: UUID,
    payload: EvidenceAssetUpdate,
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
) -> EvidenceAssetOut:
    fields = payload.model_dump(exclude_unset=True)
    if "owner_type" in fields and fields["owner_type"] is not None:
        _validate_evidence_owner_type(fields["owner_type"])
    if "file_path" in fields and fields["file_path"] is not None:
        fields["file_path"] = _validate_managed_asset_path(fields["file_path"], settings=settings)
    row = _repo.update_evidence_asset(conn, record_id, **fields)
    if row is None:
        raise HTTPException(status_code=404, detail="evidence asset not found")
    return _evidence_asset_out(row)


@router.delete("/master-data/evidence-assets/{record_id}")
async def delete_evidence_asset(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_evidence_asset(conn, record_id):
        raise HTTPException(status_code=404, detail="evidence asset not found")
    return {"deleted": True}


@router.get("/master-data/evidence-assets/{record_id}/download")
async def download_evidence_asset(
    record_id: UUID,
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    row = _repo.get_evidence_asset(conn, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="evidence asset not found")
    file_path = _validate_managed_asset_path(row.file_path, settings=settings)
    media_type = row.media_type or "application/octet-stream"
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=row.file_name,
    )
