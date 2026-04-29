from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.master_data_repo import MasterDataRepository


router = APIRouter(tags=["master-data"])

_repo = MasterDataRepository()


class CompanyProfileBase(BaseModel):
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


class PersonProfileBase(BaseModel):
    full_name: str = Field(min_length=1)
    gender: str | None = None
    age: int | None = None
    education: str | None = None
    title: str | None = None
    role_name: str | None = None
    specialty: str | None = None
    years_experience: int | None = None
    phone: str | None = None
    email: str | None = None
    resume_text: str | None = None
    profile_json: dict[str, Any] = Field(default_factory=dict)


class PersonProfileCreate(PersonProfileBase):
    pass


class PersonProfileUpdate(BaseModel):
    full_name: str | None = None
    gender: str | None = None
    age: int | None = None
    education: str | None = None
    title: str | None = None
    role_name: str | None = None
    specialty: str | None = None
    years_experience: int | None = None
    phone: str | None = None
    email: str | None = None
    resume_text: str | None = None
    profile_json: dict[str, Any] | None = None


class PersonProfileOut(PersonProfileBase):
    id: UUID
    created_at: str
    updated_at: str


class ProjectPerformanceBase(BaseModel):
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


class QualificationCertificateBase(BaseModel):
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


class FinancialStatementBase(BaseModel):
    fiscal_year: int
    statement_type: str = Field(min_length=1)
    statement_data: dict[str, Any] = Field(default_factory=dict)
    source_note: str | None = None


class FinancialStatementCreate(FinancialStatementBase):
    pass


class FinancialStatementUpdate(BaseModel):
    fiscal_year: int | None = None
    statement_type: str | None = None
    statement_data: dict[str, Any] | None = None
    source_note: str | None = None


class FinancialStatementOut(FinancialStatementBase):
    id: UUID
    created_at: str
    updated_at: str


class EvidenceAssetBase(BaseModel):
    owner_type: str = Field(min_length=1)
    owner_id: UUID | None = None
    asset_name: str = Field(min_length=1)
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
    owner_type: str | None = None
    owner_id: UUID | None = None
    asset_name: str | None = None
    asset_type: str | None = None
    file_name: str | None = None
    file_path: str | None = None
    media_type: str | None = None
    issuer_name: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    metadata_json: dict[str, Any] | None = None
    sort_order: int | None = None


class EvidenceAssetOut(EvidenceAssetBase):
    id: UUID
    created_at: str
    updated_at: str


def _company_out(row) -> CompanyProfileOut:
    return CompanyProfileOut(
        id=row.id,
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


def _person_out(row) -> PersonProfileOut:
    return PersonProfileOut(
        id=row.id,
        full_name=row.full_name,
        gender=row.gender,
        age=row.age,
        education=row.education,
        title=row.title,
        role_name=row.role_name,
        specialty=row.specialty,
        years_experience=row.years_experience,
        phone=row.phone,
        email=row.email,
        resume_text=row.resume_text,
        profile_json=row.profile_json,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _performance_out(row) -> ProjectPerformanceOut:
    return ProjectPerformanceOut(
        id=row.id,
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


def _certificate_out(row) -> QualificationCertificateOut:
    return QualificationCertificateOut(
        id=row.id,
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


def _financial_out(row) -> FinancialStatementOut:
    return FinancialStatementOut(
        id=row.id,
        fiscal_year=row.fiscal_year,
        statement_type=row.statement_type,
        statement_data=row.statement_data,
        source_note=row.source_note,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _evidence_asset_out(row) -> EvidenceAssetOut:
    return EvidenceAssetOut(
        id=row.id,
        owner_type=row.owner_type,
        owner_id=row.owner_id,
        asset_name=row.asset_name,
        asset_type=row.asset_type,
        file_name=row.file_name,
        file_path=row.file_path,
        media_type=row.media_type,
        issuer_name=row.issuer_name,
        issued_on=row.issued_on,
        expires_on=row.expires_on,
        metadata_json=row.metadata_json,
        sort_order=row.sort_order,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _not_found(detail: str):
    raise HTTPException(status_code=404, detail=detail)


def _validate_evidence_owner_type(value: str) -> str:
    allowed = {
        "company_profile",
        "person_profile",
        "project_performance",
        "qualification_certificate",
        "financial_statement",
    }
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"unsupported evidence owner_type: {value}")
    return value


@router.get("/master-data/company-profiles", response_model=list[CompanyProfileOut])
async def list_company_profiles(conn: Connection = Depends(get_db_conn)) -> list[CompanyProfileOut]:
    return [_company_out(row) for row in _repo.list_company_profiles(conn)]


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


@router.get("/master-data/people", response_model=list[PersonProfileOut])
async def list_people(conn: Connection = Depends(get_db_conn)) -> list[PersonProfileOut]:
    return [_person_out(row) for row in _repo.list_people(conn)]


@router.post("/master-data/people", response_model=PersonProfileOut, status_code=201)
async def create_person(payload: PersonProfileCreate, conn: Connection = Depends(get_db_conn)) -> PersonProfileOut:
    return _person_out(_repo.create_person(conn, **payload.model_dump()))


@router.put("/master-data/people/{record_id}", response_model=PersonProfileOut)
async def update_person(record_id: UUID, payload: PersonProfileUpdate, conn: Connection = Depends(get_db_conn)) -> PersonProfileOut:
    row = _repo.update_person(conn, record_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        _not_found("person profile not found")
    return _person_out(row)


@router.delete("/master-data/people/{record_id}")
async def delete_person(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_person(conn, record_id):
        _not_found("person profile not found")
    return {"deleted": True}


@router.get("/master-data/performances", response_model=list[ProjectPerformanceOut])
async def list_performances(conn: Connection = Depends(get_db_conn)) -> list[ProjectPerformanceOut]:
    return [_performance_out(row) for row in _repo.list_project_performances(conn)]


@router.post("/master-data/performances", response_model=ProjectPerformanceOut, status_code=201)
async def create_performance(payload: ProjectPerformanceCreate, conn: Connection = Depends(get_db_conn)) -> ProjectPerformanceOut:
    return _performance_out(_repo.create_project_performance(conn, **payload.model_dump()))


@router.put("/master-data/performances/{record_id}", response_model=ProjectPerformanceOut)
async def update_performance(record_id: UUID, payload: ProjectPerformanceUpdate, conn: Connection = Depends(get_db_conn)) -> ProjectPerformanceOut:
    row = _repo.update_project_performance(conn, record_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        _not_found("project performance not found")
    return _performance_out(row)


@router.delete("/master-data/performances/{record_id}")
async def delete_performance(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_project_performance(conn, record_id):
        _not_found("project performance not found")
    return {"deleted": True}


@router.get("/master-data/certificates", response_model=list[QualificationCertificateOut])
async def list_certificates(conn: Connection = Depends(get_db_conn)) -> list[QualificationCertificateOut]:
    return [_certificate_out(row) for row in _repo.list_certificates(conn)]


@router.post("/master-data/certificates", response_model=QualificationCertificateOut, status_code=201)
async def create_certificate(payload: QualificationCertificateCreate, conn: Connection = Depends(get_db_conn)) -> QualificationCertificateOut:
    return _certificate_out(_repo.create_certificate(conn, **payload.model_dump()))


@router.put("/master-data/certificates/{record_id}", response_model=QualificationCertificateOut)
async def update_certificate(record_id: UUID, payload: QualificationCertificateUpdate, conn: Connection = Depends(get_db_conn)) -> QualificationCertificateOut:
    row = _repo.update_certificate(conn, record_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        _not_found("qualification certificate not found")
    return _certificate_out(row)


@router.delete("/master-data/certificates/{record_id}")
async def delete_certificate(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_certificate(conn, record_id):
        _not_found("qualification certificate not found")
    return {"deleted": True}


@router.get("/master-data/financial-statements", response_model=list[FinancialStatementOut])
async def list_financial_statements(conn: Connection = Depends(get_db_conn)) -> list[FinancialStatementOut]:
    return [_financial_out(row) for row in _repo.list_financial_statements(conn)]


@router.post("/master-data/financial-statements", response_model=FinancialStatementOut, status_code=201)
async def create_financial_statement(payload: FinancialStatementCreate, conn: Connection = Depends(get_db_conn)) -> FinancialStatementOut:
    try:
        row = _repo.create_financial_statement(conn, **payload.model_dump())
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="financial statement already exists for year/type") from exc
        raise
    return _financial_out(row)


@router.put("/master-data/financial-statements/{record_id}", response_model=FinancialStatementOut)
async def update_financial_statement(record_id: UUID, payload: FinancialStatementUpdate, conn: Connection = Depends(get_db_conn)) -> FinancialStatementOut:
    try:
        row = _repo.update_financial_statement(conn, record_id, **payload.model_dump(exclude_unset=True))
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="financial statement already exists for year/type") from exc
        raise
    if row is None:
        _not_found("financial statement not found")
    return _financial_out(row)


@router.delete("/master-data/financial-statements/{record_id}")
async def delete_financial_statement(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_financial_statement(conn, record_id):
        _not_found("financial statement not found")
    return {"deleted": True}


@router.get("/master-data/evidence-assets", response_model=list[EvidenceAssetOut])
async def list_evidence_assets(conn: Connection = Depends(get_db_conn)) -> list[EvidenceAssetOut]:
    return [_evidence_asset_out(row) for row in _repo.list_evidence_assets(conn)]


@router.post("/master-data/evidence-assets", response_model=EvidenceAssetOut, status_code=201)
async def create_evidence_asset(payload: EvidenceAssetCreate, conn: Connection = Depends(get_db_conn)) -> EvidenceAssetOut:
    _validate_evidence_owner_type(payload.owner_type)
    return _evidence_asset_out(_repo.create_evidence_asset(conn, **payload.model_dump()))


@router.put("/master-data/evidence-assets/{record_id}", response_model=EvidenceAssetOut)
async def update_evidence_asset(record_id: UUID, payload: EvidenceAssetUpdate, conn: Connection = Depends(get_db_conn)) -> EvidenceAssetOut:
    fields = payload.model_dump(exclude_unset=True)
    if "owner_type" in fields and fields["owner_type"] is not None:
        _validate_evidence_owner_type(fields["owner_type"])
    row = _repo.update_evidence_asset(conn, record_id, **fields)
    if row is None:
        _not_found("evidence asset not found")
    return _evidence_asset_out(row)


@router.delete("/master-data/evidence-assets/{record_id}")
async def delete_evidence_asset(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_evidence_asset(conn, record_id):
        _not_found("evidence asset not found")
    return {"deleted": True}
