from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.master_data_repo import MasterDataRepository


router = APIRouter(tags=["master-data"], dependencies=[Depends(get_current_user)])

_repo = MasterDataRepository()


def _not_found(detail: str) -> None:
    raise HTTPException(status_code=404, detail=detail)


def _default_company_key(company_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.casefold()).strip("-")
    return slug or f"company-{uuid4().hex[:8]}"


class LibraryCompanyBase(BaseModel):
    company_name: str = Field(min_length=1)
    company_key: str | None = None
    company_type: str | None = None
    enabled: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class LibraryCompanyCreate(LibraryCompanyBase):
    pass


class LibraryCompanyUpdate(BaseModel):
    company_name: str | None = None
    company_key: str | None = None
    company_type: str | None = None
    enabled: bool | None = None
    metadata_json: dict[str, Any] | None = None


class LibraryCompanyOut(LibraryCompanyBase):
    id: UUID
    company_key: str
    created_at: str
    updated_at: str


class CompanyProfileBase(BaseModel):
    library_company_id: UUID | None = None
    company_name: str = Field(min_length=1)
    company_code: str | None = None
    unified_social_credit_code: str | None = None
    registered_address: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    website: str | None = None
    registered_capital: str | None = None
    company_type: str | None = None
    business_scope: str | None = None
    profile_json: dict[str, Any] = Field(default_factory=dict)


class CompanyProfileCreate(CompanyProfileBase):
    pass


class CompanyProfileUpdate(BaseModel):
    library_company_id: UUID | None = None
    company_name: str | None = None
    company_code: str | None = None
    unified_social_credit_code: str | None = None
    registered_address: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    website: str | None = None
    registered_capital: str | None = None
    company_type: str | None = None
    business_scope: str | None = None
    profile_json: dict[str, Any] | None = None


class CompanyProfileOut(CompanyProfileBase):
    id: UUID
    created_at: str
    updated_at: str


def _library_company_out(row) -> LibraryCompanyOut:
    return LibraryCompanyOut(
        id=row.id,
        company_key=row.company_key,
        company_name=row.company_name,
        company_type=row.company_type,
        enabled=row.enabled,
        metadata_json=row.metadata_json,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _company_out(row) -> CompanyProfileOut:
    return CompanyProfileOut(
        id=row.id,
        library_company_id=row.library_company_id,
        company_name=row.company_name,
        company_code=row.company_code,
        unified_social_credit_code=row.unified_social_credit_code,
        registered_address=row.registered_address,
        contact_name=row.contact_name,
        contact_phone=row.contact_phone,
        contact_email=row.contact_email,
        website=row.website,
        registered_capital=row.registered_capital,
        company_type=row.company_type,
        business_scope=row.business_scope,
        profile_json=row.profile_json,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/master-data/library-companies", response_model=list[LibraryCompanyOut])
async def list_library_companies(conn: Connection = Depends(get_db_conn)) -> list[LibraryCompanyOut]:
    return [_library_company_out(row) for row in _repo.list_library_companies(conn)]


@router.post("/master-data/library-companies", response_model=LibraryCompanyOut, status_code=201)
async def create_library_company(payload: LibraryCompanyCreate, conn: Connection = Depends(get_db_conn)) -> LibraryCompanyOut:
    body = payload.model_dump()
    body["company_key"] = (body.get("company_key") or "").strip() or _default_company_key(body["company_name"])
    return _library_company_out(_repo.create_library_company(conn, **body))


@router.put("/master-data/library-companies/{record_id}", response_model=LibraryCompanyOut)
async def update_library_company(record_id: UUID, payload: LibraryCompanyUpdate, conn: Connection = Depends(get_db_conn)) -> LibraryCompanyOut:
    row = _repo.update_library_company(conn, record_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        _not_found("library company not found")
    return _library_company_out(row)


@router.delete("/master-data/library-companies/{record_id}")
async def delete_library_company(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_library_company(conn, record_id):
        _not_found("library company not found")
    return {"deleted": True}


@router.get("/master-data/company-profiles", response_model=list[CompanyProfileOut])
async def list_company_profiles(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[CompanyProfileOut]:
    return [_company_out(row) for row in _repo.list_company_profiles(conn, library_company_id=library_company_id)]


@router.post("/master-data/company-profiles", response_model=CompanyProfileOut, status_code=201)
async def create_company_profile(payload: CompanyProfileCreate, conn: Connection = Depends(get_db_conn)) -> CompanyProfileOut:
    return _company_out(_repo.create_company_profile(conn, **payload.model_dump()))


@router.put("/master-data/company-profiles/{record_id}", response_model=CompanyProfileOut)
async def update_company_profile(record_id: UUID, payload: CompanyProfileUpdate, conn: Connection = Depends(get_db_conn)) -> CompanyProfileOut:
    row = _repo.update_company_profile(conn, record_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        _not_found("company profile not found")
    return _company_out(row)


@router.delete("/master-data/company-profiles/{record_id}")
async def delete_company_profile(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_company_profile(conn, record_id):
        _not_found("company profile not found")
    return {"deleted": True}
