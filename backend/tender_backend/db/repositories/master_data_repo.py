from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class CompanyProfileRow:
    id: UUID
    company_name: str
    company_code: str | None
    unified_social_credit_code: str | None
    registered_address: str | None
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    website: str | None
    registered_capital: str | None
    company_type: str | None
    business_scope: str | None
    profile_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PersonProfileRow:
    id: UUID
    full_name: str
    gender: str | None
    age: int | None
    education: str | None
    title: str | None
    role_name: str | None
    specialty: str | None
    years_experience: int | None
    phone: str | None
    email: str | None
    resume_text: str | None
    profile_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectPerformanceRow:
    id: UUID
    project_name: str
    client_name: str
    contract_amount: Decimal | None
    currency: str
    started_on: date | None
    ended_on: date | None
    project_status: str | None
    service_scope: str | None
    peak_staffing: int | None
    average_staffing: int | None
    contact_name: str | None
    contact_phone: str | None
    evidence_summary: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class QualificationCertificateRow:
    id: UUID
    certificate_name: str
    certificate_type: str | None
    certificate_no: str | None
    holder_name: str | None
    grade: str | None
    specialty: str | None
    issued_by: str | None
    valid_from: date | None
    valid_to: date | None
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class FinancialStatementRow:
    id: UUID
    fiscal_year: int
    statement_type: str
    statement_data: dict[str, Any]
    source_note: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvidenceAssetRow:
    id: UUID
    owner_type: str
    owner_id: UUID | None
    asset_name: str
    asset_type: str
    file_name: str
    file_path: str
    media_type: str | None
    issuer_name: str | None
    issued_on: date | None
    expires_on: date | None
    metadata_json: dict[str, Any]
    sort_order: int
    created_at: datetime
    updated_at: datetime


_COMPANY_COLUMNS = (
    "id, company_name, company_code, unified_social_credit_code, registered_address, "
    "contact_name, contact_phone, contact_email, website, registered_capital, "
    "company_type, business_scope, profile_json, created_at, updated_at"
)
_PERSON_COLUMNS = (
    "id, full_name, gender, age, education, title, role_name, specialty, "
    "years_experience, phone, email, resume_text, profile_json, created_at, updated_at"
)
_PERFORMANCE_COLUMNS = (
    "id, project_name, client_name, contract_amount, currency, started_on, ended_on, "
    "project_status, service_scope, peak_staffing, average_staffing, contact_name, "
    "contact_phone, evidence_summary, metadata_json, created_at, updated_at"
)
_CERTIFICATE_COLUMNS = (
    "id, certificate_name, certificate_type, certificate_no, holder_name, grade, "
    "specialty, issued_by, valid_from, valid_to, status, metadata_json, created_at, updated_at"
)
_FINANCIAL_COLUMNS = (
    "id, fiscal_year, statement_type, statement_data, source_note, created_at, updated_at"
)
_EVIDENCE_COLUMNS = (
    "id, owner_type, owner_id, asset_name, asset_type, file_name, file_path, media_type, "
    "issuer_name, issued_on, expires_on, metadata_json, sort_order, created_at, updated_at"
)


def _to_company(row: dict[str, Any]) -> CompanyProfileRow:
    return CompanyProfileRow(
        id=row["id"],
        company_name=row["company_name"],
        company_code=row["company_code"],
        unified_social_credit_code=row["unified_social_credit_code"],
        registered_address=row["registered_address"],
        contact_name=row["contact_name"],
        contact_phone=row["contact_phone"],
        contact_email=row["contact_email"],
        website=row["website"],
        registered_capital=row["registered_capital"],
        company_type=row["company_type"],
        business_scope=row["business_scope"],
        profile_json=dict(row["profile_json"] or {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_person(row: dict[str, Any]) -> PersonProfileRow:
    return PersonProfileRow(
        id=row["id"],
        full_name=row["full_name"],
        gender=row["gender"],
        age=row["age"],
        education=row["education"],
        title=row["title"],
        role_name=row["role_name"],
        specialty=row["specialty"],
        years_experience=row["years_experience"],
        phone=row["phone"],
        email=row["email"],
        resume_text=row["resume_text"],
        profile_json=dict(row["profile_json"] or {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_performance(row: dict[str, Any]) -> ProjectPerformanceRow:
    return ProjectPerformanceRow(
        id=row["id"],
        project_name=row["project_name"],
        client_name=row["client_name"],
        contract_amount=row["contract_amount"],
        currency=row["currency"],
        started_on=row["started_on"],
        ended_on=row["ended_on"],
        project_status=row["project_status"],
        service_scope=row["service_scope"],
        peak_staffing=row["peak_staffing"],
        average_staffing=row["average_staffing"],
        contact_name=row["contact_name"],
        contact_phone=row["contact_phone"],
        evidence_summary=row["evidence_summary"],
        metadata_json=dict(row["metadata_json"] or {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_certificate(row: dict[str, Any]) -> QualificationCertificateRow:
    return QualificationCertificateRow(
        id=row["id"],
        certificate_name=row["certificate_name"],
        certificate_type=row["certificate_type"],
        certificate_no=row["certificate_no"],
        holder_name=row["holder_name"],
        grade=row["grade"],
        specialty=row["specialty"],
        issued_by=row["issued_by"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        status=row["status"],
        metadata_json=dict(row["metadata_json"] or {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_financial(row: dict[str, Any]) -> FinancialStatementRow:
    return FinancialStatementRow(
        id=row["id"],
        fiscal_year=row["fiscal_year"],
        statement_type=row["statement_type"],
        statement_data=dict(row["statement_data"] or {}),
        source_note=row["source_note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_evidence_asset(row: dict[str, Any]) -> EvidenceAssetRow:
    return EvidenceAssetRow(
        id=row["id"],
        owner_type=row["owner_type"],
        owner_id=row["owner_id"],
        asset_name=row["asset_name"],
        asset_type=row["asset_type"],
        file_name=row["file_name"],
        file_path=row["file_path"],
        media_type=row["media_type"],
        issuer_name=row["issuer_name"],
        issued_on=row["issued_on"],
        expires_on=row["expires_on"],
        metadata_json=dict(row["metadata_json"] or {}),
        sort_order=row["sort_order"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class MasterDataRepository:
    def list_company_profiles(self, conn: Connection) -> list[CompanyProfileRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_COMPANY_COLUMNS} FROM company_profile ORDER BY created_at DESC"
            ).fetchall()
        return [_to_company(row) for row in rows]

    def get_company_profile(self, conn: Connection, record_id: UUID) -> CompanyProfileRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_COMPANY_COLUMNS} FROM company_profile WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_company(row) if row else None

    def create_company_profile(self, conn: Connection, **fields: Any) -> CompanyProfileRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO company_profile (
                  id, company_name, company_code, unified_social_credit_code, registered_address,
                  contact_name, contact_phone, contact_email, website, registered_capital,
                  company_type, business_scope, profile_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING {_COMPANY_COLUMNS}
                """,
                (
                    uuid4(),
                    fields["company_name"],
                    fields.get("company_code"),
                    fields.get("unified_social_credit_code"),
                    fields.get("registered_address"),
                    fields.get("contact_name"),
                    fields.get("contact_phone"),
                    fields.get("contact_email"),
                    fields.get("website"),
                    fields.get("registered_capital"),
                    fields.get("company_type"),
                    fields.get("business_scope"),
                    json.dumps(fields.get("profile_json") or {}, ensure_ascii=False),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_company(row)

    def update_company_profile(self, conn: Connection, record_id: UUID, **fields: Any) -> CompanyProfileRow | None:
        return self._update_json_record(
            conn,
            table="company_profile",
            record_id=record_id,
            fields=fields,
            allowed_fields={
                "company_name", "company_code", "unified_social_credit_code", "registered_address",
                "contact_name", "contact_phone", "contact_email", "website", "registered_capital",
                "company_type", "business_scope", "profile_json",
            },
            json_fields={"profile_json"},
            returning=_COMPANY_COLUMNS,
            mapper=_to_company,
        )

    def delete_company_profile(self, conn: Connection, record_id: UUID) -> bool:
        return self._delete(conn, table="company_profile", record_id=record_id)

    def list_people(self, conn: Connection) -> list[PersonProfileRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_PERSON_COLUMNS} FROM person_profile ORDER BY created_at DESC"
            ).fetchall()
        return [_to_person(row) for row in rows]

    def get_person(self, conn: Connection, record_id: UUID) -> PersonProfileRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_PERSON_COLUMNS} FROM person_profile WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_person(row) if row else None

    def create_person(self, conn: Connection, **fields: Any) -> PersonProfileRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO person_profile (
                  id, full_name, gender, age, education, title, role_name, specialty,
                  years_experience, phone, email, resume_text, profile_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING {_PERSON_COLUMNS}
                """,
                (
                    uuid4(),
                    fields["full_name"],
                    fields.get("gender"),
                    fields.get("age"),
                    fields.get("education"),
                    fields.get("title"),
                    fields.get("role_name"),
                    fields.get("specialty"),
                    fields.get("years_experience"),
                    fields.get("phone"),
                    fields.get("email"),
                    fields.get("resume_text"),
                    json.dumps(fields.get("profile_json") or {}, ensure_ascii=False),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_person(row)

    def update_person(self, conn: Connection, record_id: UUID, **fields: Any) -> PersonProfileRow | None:
        return self._update_json_record(
            conn,
            table="person_profile",
            record_id=record_id,
            fields=fields,
            allowed_fields={
                "full_name", "gender", "age", "education", "title", "role_name", "specialty",
                "years_experience", "phone", "email", "resume_text", "profile_json",
            },
            json_fields={"profile_json"},
            returning=_PERSON_COLUMNS,
            mapper=_to_person,
        )

    def delete_person(self, conn: Connection, record_id: UUID) -> bool:
        return self._delete(conn, table="person_profile", record_id=record_id)

    def list_project_performances(self, conn: Connection) -> list[ProjectPerformanceRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_PERFORMANCE_COLUMNS} FROM project_performance ORDER BY started_on DESC NULLS LAST, created_at DESC"
            ).fetchall()
        return [_to_performance(row) for row in rows]

    def get_project_performance(self, conn: Connection, record_id: UUID) -> ProjectPerformanceRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_PERFORMANCE_COLUMNS} FROM project_performance WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_performance(row) if row else None

    def create_project_performance(self, conn: Connection, **fields: Any) -> ProjectPerformanceRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO project_performance (
                  id, project_name, client_name, contract_amount, currency, started_on, ended_on,
                  project_status, service_scope, peak_staffing, average_staffing, contact_name,
                  contact_phone, evidence_summary, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING {_PERFORMANCE_COLUMNS}
                """,
                (
                    uuid4(),
                    fields["project_name"],
                    fields["client_name"],
                    fields.get("contract_amount"),
                    fields.get("currency") or "CNY",
                    fields.get("started_on"),
                    fields.get("ended_on"),
                    fields.get("project_status"),
                    fields.get("service_scope"),
                    fields.get("peak_staffing"),
                    fields.get("average_staffing"),
                    fields.get("contact_name"),
                    fields.get("contact_phone"),
                    fields.get("evidence_summary"),
                    json.dumps(fields.get("metadata_json") or {}, ensure_ascii=False),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_performance(row)

    def update_project_performance(self, conn: Connection, record_id: UUID, **fields: Any) -> ProjectPerformanceRow | None:
        return self._update_json_record(
            conn,
            table="project_performance",
            record_id=record_id,
            fields=fields,
            allowed_fields={
                "project_name", "client_name", "contract_amount", "currency", "started_on",
                "ended_on", "project_status", "service_scope", "peak_staffing",
                "average_staffing", "contact_name", "contact_phone", "evidence_summary",
                "metadata_json",
            },
            json_fields={"metadata_json"},
            returning=_PERFORMANCE_COLUMNS,
            mapper=_to_performance,
        )

    def delete_project_performance(self, conn: Connection, record_id: UUID) -> bool:
        return self._delete(conn, table="project_performance", record_id=record_id)

    def list_certificates(self, conn: Connection) -> list[QualificationCertificateRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_CERTIFICATE_COLUMNS} FROM qualification_certificate ORDER BY valid_to DESC NULLS LAST, created_at DESC"
            ).fetchall()
        return [_to_certificate(row) for row in rows]

    def get_certificate(self, conn: Connection, record_id: UUID) -> QualificationCertificateRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_CERTIFICATE_COLUMNS} FROM qualification_certificate WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_certificate(row) if row else None

    def create_certificate(self, conn: Connection, **fields: Any) -> QualificationCertificateRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO qualification_certificate (
                  id, certificate_name, certificate_type, certificate_no, holder_name, grade,
                  specialty, issued_by, valid_from, valid_to, status, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING {_CERTIFICATE_COLUMNS}
                """,
                (
                    uuid4(),
                    fields["certificate_name"],
                    fields.get("certificate_type"),
                    fields.get("certificate_no"),
                    fields.get("holder_name"),
                    fields.get("grade"),
                    fields.get("specialty"),
                    fields.get("issued_by"),
                    fields.get("valid_from"),
                    fields.get("valid_to"),
                    fields.get("status") or "active",
                    json.dumps(fields.get("metadata_json") or {}, ensure_ascii=False),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_certificate(row)

    def update_certificate(self, conn: Connection, record_id: UUID, **fields: Any) -> QualificationCertificateRow | None:
        return self._update_json_record(
            conn,
            table="qualification_certificate",
            record_id=record_id,
            fields=fields,
            allowed_fields={
                "certificate_name", "certificate_type", "certificate_no", "holder_name", "grade",
                "specialty", "issued_by", "valid_from", "valid_to", "status", "metadata_json",
            },
            json_fields={"metadata_json"},
            returning=_CERTIFICATE_COLUMNS,
            mapper=_to_certificate,
        )

    def delete_certificate(self, conn: Connection, record_id: UUID) -> bool:
        return self._delete(conn, table="qualification_certificate", record_id=record_id)

    def list_financial_statements(self, conn: Connection) -> list[FinancialStatementRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_FINANCIAL_COLUMNS} FROM financial_statement ORDER BY fiscal_year DESC, statement_type"
            ).fetchall()
        return [_to_financial(row) for row in rows]

    def get_financial_statement(self, conn: Connection, record_id: UUID) -> FinancialStatementRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_FINANCIAL_COLUMNS} FROM financial_statement WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_financial(row) if row else None

    def create_financial_statement(self, conn: Connection, **fields: Any) -> FinancialStatementRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO financial_statement (
                  id, fiscal_year, statement_type, statement_data, source_note
                )
                VALUES (%s, %s, %s, %s::jsonb, %s)
                RETURNING {_FINANCIAL_COLUMNS}
                """,
                (
                    uuid4(),
                    fields["fiscal_year"],
                    fields["statement_type"],
                    json.dumps(fields.get("statement_data") or {}, ensure_ascii=False),
                    fields.get("source_note"),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_financial(row)

    def update_financial_statement(self, conn: Connection, record_id: UUID, **fields: Any) -> FinancialStatementRow | None:
        return self._update_json_record(
            conn,
            table="financial_statement",
            record_id=record_id,
            fields=fields,
            allowed_fields={"fiscal_year", "statement_type", "statement_data", "source_note"},
            json_fields={"statement_data"},
            returning=_FINANCIAL_COLUMNS,
            mapper=_to_financial,
        )

    def delete_financial_statement(self, conn: Connection, record_id: UUID) -> bool:
        return self._delete(conn, table="financial_statement", record_id=record_id)

    def list_evidence_assets(self, conn: Connection) -> list[EvidenceAssetRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_EVIDENCE_COLUMNS} FROM evidence_asset ORDER BY owner_type, sort_order, created_at DESC"
            ).fetchall()
        return [_to_evidence_asset(row) for row in rows]

    def get_evidence_asset(self, conn: Connection, record_id: UUID) -> EvidenceAssetRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_EVIDENCE_COLUMNS} FROM evidence_asset WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_evidence_asset(row) if row else None

    def create_evidence_asset(self, conn: Connection, **fields: Any) -> EvidenceAssetRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO evidence_asset (
                  id, owner_type, owner_id, asset_name, asset_type, file_name, file_path,
                  media_type, issuer_name, issued_on, expires_on, metadata_json, sort_order
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING {_EVIDENCE_COLUMNS}
                """,
                (
                    uuid4(),
                    fields["owner_type"],
                    fields.get("owner_id"),
                    fields["asset_name"],
                    fields.get("asset_type") or "supporting_document",
                    fields["file_name"],
                    fields["file_path"],
                    fields.get("media_type"),
                    fields.get("issuer_name"),
                    fields.get("issued_on"),
                    fields.get("expires_on"),
                    json.dumps(fields.get("metadata_json") or {}, ensure_ascii=False),
                    fields.get("sort_order") or 0,
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_evidence_asset(row)

    def update_evidence_asset(self, conn: Connection, record_id: UUID, **fields: Any) -> EvidenceAssetRow | None:
        return self._update_json_record(
            conn,
            table="evidence_asset",
            record_id=record_id,
            fields=fields,
            allowed_fields={
                "owner_type", "owner_id", "asset_name", "asset_type", "file_name", "file_path",
                "media_type", "issuer_name", "issued_on", "expires_on", "metadata_json",
                "sort_order",
            },
            json_fields={"metadata_json"},
            returning=_EVIDENCE_COLUMNS,
            mapper=_to_evidence_asset,
        )

    def delete_evidence_asset(self, conn: Connection, record_id: UUID) -> bool:
        return self._delete(conn, table="evidence_asset", record_id=record_id)

    def _update_json_record(
        self,
        conn: Connection,
        *,
        table: str,
        record_id: UUID,
        fields: dict[str, Any],
        allowed_fields: set[str],
        json_fields: set[str],
        returning: str,
        mapper,
    ):
        sets: list[str] = []
        values: list[Any] = []
        for field in allowed_fields:
            if field not in fields:
                continue
            value = fields[field]
            if field in json_fields:
                sets.append(f"{field} = %s::jsonb")
                values.append(json.dumps(value or {}, ensure_ascii=False))
            else:
                sets.append(f"{field} = %s")
                values.append(value)

        if not sets:
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute(
                    f"SELECT {returning} FROM {table} WHERE id = %s",
                    (record_id,),
                ).fetchone()
            return mapper(row) if row else None

        sets.append("updated_at = now()")
        values.append(record_id)

        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE {table}
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING {returning}
                """,
                values,
            ).fetchone()
        conn.commit()
        return mapper(row) if row else None

    def _delete(self, conn: Connection, *, table: str, record_id: UUID) -> bool:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {table} WHERE id = %s", (record_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
