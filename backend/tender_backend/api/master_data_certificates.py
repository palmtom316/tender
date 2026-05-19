from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.master_data_repo import (
    POWER_CERTIFICATE_GRADES,
    POWER_CERTIFICATE_TYPES,
    POWER_PERFORMANCE_METADATA_FIELDS,
    MasterDataRepository,
)


router = APIRouter(tags=["master-data"], dependencies=[Depends(get_current_user)])

_repo = MasterDataRepository()


def _not_found(detail: str) -> None:
    raise HTTPException(status_code=404, detail=detail)


class QualificationCertificateBase(BaseModel):
    library_company_id: UUID | None = None
    certificate_name: str = Field(min_length=1)
    certificate_type: str | None = None
    certificate_no: str | None = None
    holder_name: str | None = None
    grade: str | None = None
    specialty: str | None = None
    issued_by: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: str = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class QualificationCertificateCreate(QualificationCertificateBase):
    pass


class QualificationCertificateUpdate(BaseModel):
    library_company_id: UUID | None = None
    certificate_name: str | None = None
    certificate_type: str | None = None
    certificate_no: str | None = None
    holder_name: str | None = None
    grade: str | None = None
    specialty: str | None = None
    issued_by: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: str | None = None
    metadata_json: dict[str, Any] | None = None


class QualificationCertificateOut(QualificationCertificateBase):
    id: UUID
    created_at: str
    updated_at: str


class PowerIndustryOptionsOut(BaseModel):
    certificate_types: list[str]
    certificate_grades: list[str]
    performance_metadata_fields: list[str]


def _certificate_out(row) -> QualificationCertificateOut:
    return QualificationCertificateOut(
        id=row.id,
        library_company_id=row.library_company_id,
        certificate_name=row.certificate_name,
        certificate_type=row.certificate_type,
        certificate_no=row.certificate_no,
        holder_name=row.holder_name,
        grade=row.grade,
        specialty=row.specialty,
        issued_by=row.issued_by,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        status=row.status,
        metadata_json=row.metadata_json,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/master-data/power-industry-options", response_model=PowerIndustryOptionsOut)
async def get_power_industry_options() -> PowerIndustryOptionsOut:
    return PowerIndustryOptionsOut(
        certificate_types=list(POWER_CERTIFICATE_TYPES),
        certificate_grades=list(POWER_CERTIFICATE_GRADES),
        performance_metadata_fields=list(POWER_PERFORMANCE_METADATA_FIELDS),
    )


@router.get("/master-data/certificates", response_model=list[QualificationCertificateOut])
async def list_certificates(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[QualificationCertificateOut]:
    return [_certificate_out(row) for row in _repo.list_certificates(conn, library_company_id=library_company_id)]


@router.post("/master-data/certificates", response_model=QualificationCertificateOut, status_code=201)
async def create_certificate(payload: QualificationCertificateCreate, conn: Connection = Depends(get_db_conn)) -> QualificationCertificateOut:
    return _certificate_out(_repo.create_certificate(conn, **payload.model_dump()))


@router.put("/master-data/certificates/{record_id}", response_model=QualificationCertificateOut)
async def update_certificate(
    record_id: UUID,
    payload: QualificationCertificateUpdate,
    conn: Connection = Depends(get_db_conn),
) -> QualificationCertificateOut:
    row = _repo.update_certificate(conn, record_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        _not_found("qualification certificate not found")
    return _certificate_out(row)


@router.delete("/master-data/certificates/{record_id}")
async def delete_certificate(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_certificate(conn, record_id):
        _not_found("qualification certificate not found")
    return {"deleted": True}
