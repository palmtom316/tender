from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.master_data_repo import MasterDataRepository


router = APIRouter(tags=["master-data"])

_repo = MasterDataRepository()
_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "master_data_assets"
_EVIDENCE_OWNER_TYPES = {
    "library_company",
    "company_profile",
    "person_profile",
    "project_performance",
    "qualification_certificate",
    "financial_statement",
}
_ASSET_TAXONOMY = [
    {
        "domain": "company_qualification",
        "label": "公司资质文件",
        "categories": [
            ("business_license", "营业执照"),
            ("company_credit_document", "公司信用文件"),
            ("legal_representative_id", "法人身份证"),
            ("enterprise_qualification", "企业资质证书及证明文件"),
            ("safety_quality_document", "安全质量证明文件"),
            ("financial_status_document", "企业财务状况"),
            ("account_information", "企业账户信息"),
            ("green_development_document", "企业绿色发展文件"),
            ("green_management_system", "绿色管理体系文件"),
            ("esg_document", "ESG文件"),
            ("green_power_certificate", "绿电绿证文件"),
            ("scientific_achievement", "科技成果文件"),
            ("innovation_incentive", "创新激励文件"),
            ("rd_team_document", "研发团队文件"),
            ("award_document", "获奖文件"),
            ("high_tech_enterprise", "高新技术企业文件"),
            ("company_name_change", "企业名称变更文件"),
        ],
    },
    {
        "domain": "company_asset",
        "label": "公司资产文件",
        "categories": [
            ("vehicle_certificate", "机动车辆证明文件"),
            ("tool_certificate", "工器具证明文件"),
            ("construction_equipment_certificate", "施工设备证明文件"),
        ],
    },
    {
        "domain": "company_performance",
        "label": "公司业绩文件",
        "categories": [
            ("similar_performance_table", "类似业绩表"),
            ("contract_document", "合同"),
            ("invoice_document", "发票"),
            ("invoice_verification", "发票验证"),
        ],
    },
    {
        "domain": "company_evaluation",
        "label": "公司履约评价",
        "categories": [
            ("performance_evaluation", "履约评价文件"),
        ],
    },
    {
        "domain": "personnel",
        "label": "人员资料",
        "categories": [
            ("performance_table", "业绩表"),
            ("id_card", "身份证"),
            ("graduation_certificate", "毕业证"),
            ("title_certificate", "职称证"),
            ("practice_certificate", "执业资格证"),
            ("safety_certificate", "安全生产合格证"),
            ("special_operation_certificate", "特种作业操作证"),
            ("social_security_proof", "社保参保证明"),
            ("labor_contract", "劳动合同书"),
        ],
    },
]


def _not_found(detail: str):
    raise HTTPException(status_code=404, detail=detail)


def _validate_evidence_owner_type(value: str) -> str:
    if value not in _EVIDENCE_OWNER_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported evidence owner_type: {value}")
    return value


def _default_company_key(company_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.casefold()).strip("-")
    return slug or f"company-{uuid4().hex[:8]}"


def _parse_json_text(raw: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{label} must be a JSON object")
    return value


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


class PersonProfileBase(BaseModel):
    library_company_id: UUID | None = None
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
    library_company_id: UUID | None = None
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


class FinancialStatementBase(BaseModel):
    library_company_id: UUID | None = None
    fiscal_year: int
    statement_type: str = Field(min_length=1)
    statement_data: dict[str, Any] = Field(default_factory=dict)
    source_note: str | None = None


class FinancialStatementCreate(FinancialStatementBase):
    pass


class FinancialStatementUpdate(BaseModel):
    library_company_id: UUID | None = None
    fiscal_year: int | None = None
    statement_type: str | None = None
    statement_data: dict[str, Any] | None = None
    source_note: str | None = None


class FinancialStatementOut(FinancialStatementBase):
    id: UUID
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


class EvidenceAssetOut(EvidenceAssetBase):
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


def _person_out(row) -> PersonProfileOut:
    return PersonProfileOut(
        id=row.id,
        library_company_id=row.library_company_id,
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


def _financial_out(row) -> FinancialStatementOut:
    return FinancialStatementOut(
        id=row.id,
        library_company_id=row.library_company_id,
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
        library_company_id=row.library_company_id,
        owner_type=row.owner_type,
        owner_id=row.owner_id,
        asset_name=row.asset_name,
        asset_domain=row.asset_domain,
        asset_category=row.asset_category,
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
    fields = payload.model_dump(exclude_unset=True)
    row = _repo.update_library_company(conn, record_id, **fields)
    if row is None:
        _not_found("library company not found")
    return _library_company_out(row)


@router.delete("/master-data/library-companies/{record_id}")
async def delete_library_company(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_library_company(conn, record_id):
        _not_found("library company not found")
    return {"deleted": True}


@router.get("/master-data/asset-taxonomy")
async def get_asset_taxonomy() -> dict[str, object]:
    return {"domains": _ASSET_TAXONOMY}


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


@router.get("/master-data/people", response_model=list[PersonProfileOut])
async def list_people(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[PersonProfileOut]:
    return [_person_out(row) for row in _repo.list_people(conn, library_company_id=library_company_id)]


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
async def list_performances(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[ProjectPerformanceOut]:
    return [_performance_out(row) for row in _repo.list_project_performances(conn, library_company_id=library_company_id)]


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
async def list_certificates(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[QualificationCertificateOut]:
    return [_certificate_out(row) for row in _repo.list_certificates(conn, library_company_id=library_company_id)]


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
async def list_financial_statements(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[FinancialStatementOut]:
    return [_financial_out(row) for row in _repo.list_financial_statements(conn, library_company_id=library_company_id)]


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
async def create_evidence_asset(payload: EvidenceAssetCreate, conn: Connection = Depends(get_db_conn)) -> EvidenceAssetOut:
    _validate_evidence_owner_type(payload.owner_type)
    return _evidence_asset_out(_repo.create_evidence_asset(conn, **payload.model_dump()))


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
) -> EvidenceAssetOut:
    _validate_evidence_owner_type(owner_type)
    payload = _parse_json_text(metadata_json, label="metadata_json")
    suffix = Path(file.filename or "").suffix
    local_name = f"{uuid4()}{suffix}"
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _UPLOAD_DIR / local_name
    content = await file.read()
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
        media_type=file.content_type or "application/octet-stream",
        issuer_name=issuer_name,
        issued_on=issued_on,
        expires_on=expires_on,
        metadata_json=payload,
        sort_order=sort_order,
    )
    return _evidence_asset_out(row)


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
