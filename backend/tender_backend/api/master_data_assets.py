from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg import Connection
from psycopg.errors import ForeignKeyViolation

from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.company_asset_repo import CompanyAssetRepository
from tender_backend.services.asset_schema import validate_common_fields


router = APIRouter(tags=["master-data"], dependencies=[Depends(get_current_user)])

_repo = CompanyAssetRepository()


class CompanyAssetBase(BaseModel):
    asset_type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    spec_model: str | None = None
    serial_no: str | None = None
    manufacturer: str | None = None
    quantity: Decimal = Field(default=Decimal("1"))
    unit: str = Field(min_length=1)
    ownership: str = Field(min_length=1)
    acquired_at: date | None = None
    expires_at: date | None = None
    technical_condition: str | None = None
    status: str = "active"
    location: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class CompanyAssetCreate(CompanyAssetBase):
    pass


class CompanyAssetUpdate(BaseModel):
    asset_type: str | None = None
    name: str | None = None
    spec_model: str | None = None
    serial_no: str | None = None
    manufacturer: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    ownership: str | None = None
    acquired_at: date | None = None
    expires_at: date | None = None
    technical_condition: str | None = None
    status: str | None = None
    location: str | None = None
    extras: dict[str, Any] | None = None
    notes: str | None = None


class CompanyAssetOut(CompanyAssetBase):
    id: UUID
    library_company_id: UUID
    created_at: str
    updated_at: str


def _asset_out(row) -> CompanyAssetOut:
    return CompanyAssetOut(
        id=row.id,
        library_company_id=row.library_company_id,
        asset_type=row.asset_type,
        name=row.name,
        spec_model=row.spec_model,
        serial_no=row.serial_no,
        manufacturer=row.manufacturer,
        quantity=row.quantity,
        unit=row.unit,
        ownership=row.ownership,
        acquired_at=row.acquired_at,
        expires_at=row.expires_at,
        technical_condition=row.technical_condition,
        status=row.status,
        location=row.location,
        extras=row.extras,
        notes=row.notes,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _validate_payload(fields: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    merged = dict(fields)
    if partial:
        existing = {
            "asset_type": merged.get("asset_type", "vehicle"),
            "name": merged.get("name", "placeholder"),
            "unit": merged.get("unit", "台"),
            "ownership": merged.get("ownership", "self"),
            "quantity": merged.get("quantity", 1),
            "status": merged.get("status", "active"),
            "extras": merged.get("extras", {}),
        }
        validate_common_fields(existing)
    else:
        validate_common_fields(merged)
    return merged


@router.get("/master-data/library-companies/{library_company_id}/assets", response_model=list[CompanyAssetOut])
async def list_company_assets(
    library_company_id: UUID,
    asset_type: str | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[CompanyAssetOut]:
    return [
        _asset_out(row)
        for row in _repo.list_assets(
            conn,
            library_company_id=library_company_id,
            asset_type=asset_type,
            status=status,
            q=q,
        )
    ]


@router.post("/master-data/library-companies/{library_company_id}/assets", response_model=CompanyAssetOut, status_code=201)
async def create_company_asset(
    library_company_id: UUID,
    payload: CompanyAssetCreate,
    conn: Connection = Depends(get_db_conn),
) -> CompanyAssetOut:
    body = payload.model_dump()
    body["library_company_id"] = library_company_id
    try:
        _validate_payload(body, partial=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _asset_out(_repo.create_asset(conn, **body))


@router.put("/master-data/assets/{record_id}", response_model=CompanyAssetOut)
async def update_company_asset(
    record_id: UUID,
    payload: CompanyAssetUpdate,
    conn: Connection = Depends(get_db_conn),
) -> CompanyAssetOut:
    fields = payload.model_dump(exclude_unset=True)
    try:
        _validate_payload(fields, partial=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = _repo.update_asset(conn, record_id, **fields)
    if row is None:
        raise HTTPException(status_code=404, detail="company asset not found")
    return _asset_out(row)


@router.delete("/master-data/assets/{record_id}")
async def delete_company_asset(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    try:
        deleted = _repo.delete_asset(conn, record_id)
    except ForeignKeyViolation as exc:
        raise HTTPException(status_code=409, detail="company asset is referenced by project equipment selection; retire it instead") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="company asset not found")
    return {"deleted": True}


@router.post("/master-data/assets/{record_id}/retire", response_model=CompanyAssetOut)
async def retire_company_asset(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> CompanyAssetOut:
    row = _repo.retire_asset(conn, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="company asset not found")
    return _asset_out(row)
