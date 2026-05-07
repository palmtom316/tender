from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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


class ContractPerformanceCreate(BaseModel):
    library_company_id: UUID
    contract_name: str = Field(min_length=1)
    party_a_company: str = Field(min_length=1)
    contract_category: str | None = None
    engineering_category: str | None = None
    contract_amount: Decimal | None = None
    contract_signed_date: date | None = None
    contract_completed_date: date | None = None
    contract_status: str | None = None
    signature_asset_id: UUID | None = None
    signature_asset_name: str | None = None
    invoice_asset_id: UUID | None = None
    invoice_asset_name: str | None = None
    invoice_verification_asset_id: UUID | None = None
    invoice_verification_asset_name: str | None = None
    performance_evaluation_asset_id: UUID | None = None
    performance_evaluation_asset_name: str | None = None


class ContractPerformanceUpdate(BaseModel):
    contract_name: str | None = None
    party_a_company: str | None = None
    contract_category: str | None = None
    engineering_category: str | None = None
    contract_amount: Decimal | None = None
    contract_signed_date: date | None = None
    contract_completed_date: date | None = None
    contract_status: str | None = None
    signature_asset_id: UUID | None = None
    signature_asset_name: str | None = None
    invoice_asset_id: UUID | None = None
    invoice_asset_name: str | None = None
    invoice_verification_asset_id: UUID | None = None
    invoice_verification_asset_name: str | None = None
    performance_evaluation_asset_id: UUID | None = None
    performance_evaluation_asset_name: str | None = None


class ContractPerformanceOut(BaseModel):
    id: UUID
    library_company_id: UUID | None = None
    auto_number: int
    contract_name: str
    party_a_company: str
    contract_category: str | None = None
    engineering_category: str | None = None
    contract_amount: Decimal | None = None
    contract_signed_date: date | None = None
    contract_completed_date: date | None = None
    contract_status: str | None = None
    signature_asset_id: UUID | None = None
    signature_asset_name: str | None = None
    invoice_asset_id: UUID | None = None
    invoice_asset_name: str | None = None
    invoice_verification_asset_id: UUID | None = None
    invoice_verification_asset_name: str | None = None
    performance_evaluation_asset_id: UUID | None = None
    performance_evaluation_asset_name: str | None = None
    created_at: str
    updated_at: str


def _asset_uuid(value: Any) -> UUID | None:
    if not value:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _contract_performance_metadata(
    *,
    contract_category: str | None,
    engineering_category: str | None,
    signature_asset_id: UUID | None,
    signature_asset_name: str | None,
    invoice_asset_id: UUID | None,
    invoice_asset_name: str | None,
    invoice_verification_asset_id: UUID | None,
    invoice_verification_asset_name: str | None,
    performance_evaluation_asset_id: UUID | None,
    performance_evaluation_asset_name: str | None,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    next_metadata = dict(current or {})
    next_metadata.update(
        {
            "contract_category": contract_category,
            "engineering_category": engineering_category,
            "signature_asset_id": str(signature_asset_id) if signature_asset_id else None,
            "signature_asset_name": signature_asset_name,
            "invoice_asset_id": str(invoice_asset_id) if invoice_asset_id else None,
            "invoice_asset_name": invoice_asset_name,
            "invoice_verification_asset_id": str(invoice_verification_asset_id) if invoice_verification_asset_id else None,
            "invoice_verification_asset_name": invoice_verification_asset_name,
            "performance_evaluation_asset_id": str(performance_evaluation_asset_id) if performance_evaluation_asset_id else None,
            "performance_evaluation_asset_name": performance_evaluation_asset_name,
        }
    )
    return next_metadata


def _contract_out(row, auto_number: int) -> ContractPerformanceOut:
    metadata = row.metadata_json or {}
    return ContractPerformanceOut(
        id=row.id,
        library_company_id=row.library_company_id,
        auto_number=auto_number,
        contract_name=row.project_name,
        party_a_company=row.client_name,
        contract_category=metadata.get("contract_category"),
        engineering_category=metadata.get("engineering_category"),
        contract_amount=row.contract_amount,
        contract_signed_date=row.started_on,
        contract_completed_date=row.ended_on,
        contract_status=row.project_status,
        signature_asset_id=_asset_uuid(metadata.get("signature_asset_id")),
        signature_asset_name=metadata.get("signature_asset_name"),
        invoice_asset_id=_asset_uuid(metadata.get("invoice_asset_id")),
        invoice_asset_name=metadata.get("invoice_asset_name"),
        invoice_verification_asset_id=_asset_uuid(metadata.get("invoice_verification_asset_id")),
        invoice_verification_asset_name=metadata.get("invoice_verification_asset_name"),
        performance_evaluation_asset_id=_asset_uuid(metadata.get("performance_evaluation_asset_id")),
        performance_evaluation_asset_name=metadata.get("performance_evaluation_asset_name"),
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


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


@router.get("/master-data/company-contract-performances", response_model=list[ContractPerformanceOut])
async def list_company_contract_performances(
    library_company_id: UUID = Query(...),
    conn: Connection = Depends(get_db_conn),
) -> list[ContractPerformanceOut]:
    rows = _repo.list_project_performances(conn, library_company_id=library_company_id)
    return [_contract_out(row, index + 1) for index, row in enumerate(rows)]


@router.post("/master-data/company-contract-performances", response_model=ContractPerformanceOut, status_code=201)
async def create_company_contract_performance(
    payload: ContractPerformanceCreate,
    conn: Connection = Depends(get_db_conn),
) -> ContractPerformanceOut:
    row = _repo.create_project_performance(
        conn,
        library_company_id=payload.library_company_id,
        project_name=payload.contract_name,
        client_name=payload.party_a_company,
        contract_amount=payload.contract_amount,
        currency="CNY",
        started_on=payload.contract_signed_date,
        ended_on=payload.contract_completed_date,
        project_status=payload.contract_status,
        metadata_json=_contract_performance_metadata(
            contract_category=payload.contract_category,
            engineering_category=payload.engineering_category,
            signature_asset_id=payload.signature_asset_id,
            signature_asset_name=payload.signature_asset_name,
            invoice_asset_id=payload.invoice_asset_id,
            invoice_asset_name=payload.invoice_asset_name,
            invoice_verification_asset_id=payload.invoice_verification_asset_id,
            invoice_verification_asset_name=payload.invoice_verification_asset_name,
            performance_evaluation_asset_id=payload.performance_evaluation_asset_id,
            performance_evaluation_asset_name=payload.performance_evaluation_asset_name,
        ),
    )
    rows = _repo.list_project_performances(conn, library_company_id=payload.library_company_id)
    auto_number = next((index + 1 for index, item in enumerate(rows) if item.id == row.id), 1)
    return _contract_out(row, auto_number)


@router.put("/master-data/company-contract-performances/{record_id}", response_model=ContractPerformanceOut)
async def update_company_contract_performance(
    record_id: UUID,
    payload: ContractPerformanceUpdate,
    conn: Connection = Depends(get_db_conn),
) -> ContractPerformanceOut:
    existing = _repo.get_project_performance(conn, record_id)
    if existing is None:
        _not_found("company contract performance not found")

    body = payload.model_dump(exclude_unset=True)
    update_fields: dict[str, Any] = {}
    if "contract_name" in body:
        update_fields["project_name"] = body["contract_name"]
    if "party_a_company" in body:
        update_fields["client_name"] = body["party_a_company"]
    if "contract_amount" in body:
        update_fields["contract_amount"] = body["contract_amount"]
    if "contract_signed_date" in body:
        update_fields["started_on"] = body["contract_signed_date"]
    if "contract_completed_date" in body:
        update_fields["ended_on"] = body["contract_completed_date"]
    if "contract_status" in body:
        update_fields["project_status"] = body["contract_status"]

    metadata_keys = {
        "contract_category",
        "engineering_category",
        "signature_asset_id",
        "signature_asset_name",
        "invoice_asset_id",
        "invoice_asset_name",
        "invoice_verification_asset_id",
        "invoice_verification_asset_name",
        "performance_evaluation_asset_id",
        "performance_evaluation_asset_name",
    }
    if metadata_keys & set(body):
        metadata = existing.metadata_json or {}
        update_fields["metadata_json"] = _contract_performance_metadata(
            contract_category=body.get("contract_category", metadata.get("contract_category")),
            engineering_category=body.get("engineering_category", metadata.get("engineering_category")),
            signature_asset_id=body.get("signature_asset_id", _asset_uuid(metadata.get("signature_asset_id"))),
            signature_asset_name=body.get("signature_asset_name", metadata.get("signature_asset_name")),
            invoice_asset_id=body.get("invoice_asset_id", _asset_uuid(metadata.get("invoice_asset_id"))),
            invoice_asset_name=body.get("invoice_asset_name", metadata.get("invoice_asset_name")),
            invoice_verification_asset_id=body.get("invoice_verification_asset_id", _asset_uuid(metadata.get("invoice_verification_asset_id"))),
            invoice_verification_asset_name=body.get("invoice_verification_asset_name", metadata.get("invoice_verification_asset_name")),
            performance_evaluation_asset_id=body.get("performance_evaluation_asset_id", _asset_uuid(metadata.get("performance_evaluation_asset_id"))),
            performance_evaluation_asset_name=body.get("performance_evaluation_asset_name", metadata.get("performance_evaluation_asset_name")),
            current=metadata,
        )

    row = _repo.update_project_performance(conn, record_id, **update_fields)
    if row is None:
        _not_found("company contract performance not found")
    rows = _repo.list_project_performances(conn, library_company_id=row.library_company_id)
    auto_number = next((index + 1 for index, item in enumerate(rows) if item.id == row.id), 1)
    return _contract_out(row, auto_number)


@router.delete("/master-data/company-contract-performances/{record_id}")
async def delete_company_contract_performance(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_project_performance(conn, record_id):
        _not_found("company contract performance not found")
    return {"deleted": True}


@router.get("/master-data/company-contract-performances/export")
async def export_company_contract_performances(
    library_company_id: UUID = Query(...),
    conn: Connection = Depends(get_db_conn),
) -> Response:
    rows = _repo.list_project_performances(conn, library_company_id=library_company_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "自动编号",
        "合同名称",
        "合同甲方单位",
        "合同类别",
        "工程类别",
        "合同金额",
        "合同签订日期",
        "合同竣工日期",
        "合同状态",
    ])
    for index, row in enumerate(rows, start=1):
        metadata = row.metadata_json or {}
        writer.writerow([
            index,
            row.project_name,
            row.client_name,
            metadata.get("contract_category") or "",
            metadata.get("engineering_category") or "",
            str(row.contract_amount) if row.contract_amount is not None else "",
            row.started_on.isoformat() if row.started_on else "",
            row.ended_on.isoformat() if row.ended_on else "",
            row.project_status or "",
        ])
    content = "\ufeff" + buffer.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="company-contract-performances.csv"'},
    )
