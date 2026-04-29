from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

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


class ProjectPerformanceBase(BaseModel):
    library_company_id: UUID | None = None
    project_name: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    contract_amount: Decimal | None = None
    currency: str = "CNY"
    started_on: date | None = None
    ended_on: date | None = None
    project_status: str | None = None
    service_scope: str | None = None
    peak_staffing: int | None = None
    average_staffing: int | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    evidence_summary: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProjectPerformanceCreate(ProjectPerformanceBase):
    pass


class ProjectPerformanceUpdate(BaseModel):
    library_company_id: UUID | None = None
    project_name: str | None = None
    client_name: str | None = None
    contract_amount: Decimal | None = None
    currency: str | None = None
    started_on: date | None = None
    ended_on: date | None = None
    project_status: str | None = None
    service_scope: str | None = None
    peak_staffing: int | None = None
    average_staffing: int | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    evidence_summary: str | None = None
    metadata_json: dict[str, Any] | None = None


class ProjectPerformanceOut(ProjectPerformanceBase):
    id: UUID
    created_at: str
    updated_at: str


def _performance_out(row) -> ProjectPerformanceOut:
    return ProjectPerformanceOut(
        id=row.id,
        library_company_id=row.library_company_id,
        project_name=row.project_name,
        client_name=row.client_name,
        contract_amount=row.contract_amount,
        currency=row.currency,
        started_on=row.started_on,
        ended_on=row.ended_on,
        project_status=row.project_status,
        service_scope=row.service_scope,
        peak_staffing=row.peak_staffing,
        average_staffing=row.average_staffing,
        contact_name=row.contact_name,
        contact_phone=row.contact_phone,
        evidence_summary=row.evidence_summary,
        metadata_json=row.metadata_json,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/master-data/performances", response_model=list[ProjectPerformanceOut])
async def list_performances(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[ProjectPerformanceOut]:
    return [_performance_out(row) for row in _repo.list_project_performances(conn, library_company_id=library_company_id)]


@router.post("/master-data/performances", response_model=ProjectPerformanceOut, status_code=201)
async def create_performance(payload: ProjectPerformanceCreate, conn: Connection = Depends(get_db_conn)) -> ProjectPerformanceOut:
    return _performance_out(_repo.create_project_performance(conn, **payload.model_dump()))


@router.put("/master-data/performances/{record_id}", response_model=ProjectPerformanceOut)
async def update_performance(
    record_id: UUID,
    payload: ProjectPerformanceUpdate,
    conn: Connection = Depends(get_db_conn),
) -> ProjectPerformanceOut:
    row = _repo.update_project_performance(conn, record_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        _not_found("project performance not found")
    return _performance_out(row)


@router.delete("/master-data/performances/{record_id}")
async def delete_performance(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_project_performance(conn, record_id):
        _not_found("project performance not found")
    return {"deleted": True}
