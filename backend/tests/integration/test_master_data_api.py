from __future__ import annotations

import os
from uuid import UUID

import psycopg
import pytest

from tender_backend.core.config import get_settings
from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _apply_master_data_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_initial_schema_sql())
    conn.execute("""
    CREATE TABLE IF NOT EXISTS company_profile (
      id UUID PRIMARY KEY,
      company_name TEXT NOT NULL,
      company_code TEXT,
      unified_social_credit_code TEXT,
      registered_address TEXT,
      contact_name TEXT,
      contact_phone TEXT,
      contact_email TEXT,
      website TEXT,
      registered_capital TEXT,
      company_type TEXT,
      business_scope TEXT,
      profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS person_profile (
      id UUID PRIMARY KEY,
      full_name TEXT NOT NULL,
      gender TEXT,
      age INT,
      education TEXT,
      title TEXT,
      role_name TEXT,
      specialty TEXT,
      years_experience INT,
      phone TEXT,
      email TEXT,
      resume_text TEXT,
      profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS project_performance (
      id UUID PRIMARY KEY,
      project_name TEXT NOT NULL,
      client_name TEXT NOT NULL,
      contract_amount NUMERIC(14,2),
      currency TEXT NOT NULL DEFAULT 'CNY',
      started_on DATE,
      ended_on DATE,
      project_status TEXT,
      service_scope TEXT,
      peak_staffing INT,
      average_staffing INT,
      contact_name TEXT,
      contact_phone TEXT,
      evidence_summary TEXT,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS qualification_certificate (
      id UUID PRIMARY KEY,
      certificate_name TEXT NOT NULL,
      certificate_type TEXT,
      certificate_no TEXT,
      holder_name TEXT,
      grade TEXT,
      specialty TEXT,
      issued_by TEXT,
      valid_from DATE,
      valid_to DATE,
      status TEXT NOT NULL DEFAULT 'active',
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS financial_statement (
      id UUID PRIMARY KEY,
      fiscal_year INT NOT NULL,
      statement_type TEXT NOT NULL,
      statement_data JSONB NOT NULL DEFAULT '{}'::jsonb,
      source_note TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (fiscal_year, statement_type)
    );
    """)
    conn.commit()


def _reset_master_data_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM financial_statement;")
    conn.execute("DELETE FROM qualification_certificate;")
    conn.execute("DELETE FROM project_performance;")
    conn.execute("DELETE FROM person_profile;")
    conn.execute("DELETE FROM company_profile;")
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_master_data_crud_flow() -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    with psycopg.connect(db_url) as conn:
        _apply_master_data_schema(conn)
        _reset_master_data_tables(conn)

    client = SyncASGIClient(app)
    try:
        company = client.post(
            "/api/master-data/company-profiles",
            json={
                "company_name": "REDACTED",
                "registered_address": "重庆市江北区金源路7号",
                "contact_name": "王莉莉",
                "contact_phone": "13800000000",
                "profile_json": {"source": "sample"},
            },
        )
        assert company.status_code == 201
        company_id = UUID(company.json()["id"])

        companies = client.get("/api/master-data/company-profiles")
        assert companies.status_code == 200
        assert any(UUID(row["id"]) == company_id for row in companies.json())

        updated_company = client.put(
            f"/api/master-data/company-profiles/{company_id}",
            json={"website": "https://example.com"},
        )
        assert updated_company.status_code == 200
        assert updated_company.json()["website"] == "https://example.com"

        person = client.post(
            "/api/master-data/people",
            json={
                "full_name": "唐玮",
                "role_name": "项目总经理",
                "specialty": "机电工程",
                "years_experience": 11,
            },
        )
        assert person.status_code == 201
        person_id = UUID(person.json()["id"])

        performance = client.post(
            "/api/master-data/performances",
            json={
                "project_name": "市区公司2024年-2025年渝中片区营配低压业务外包服务",
                "client_name": "REDACTED市区供电分公司",
                "contract_amount": 944.39,
                "currency": "CNY",
                "started_on": "2024-01-01",
                "ended_on": "2025-12-31",
                "peak_staffing": 155,
                "average_staffing": 150,
            },
        )
        assert performance.status_code == 201
        performance_id = UUID(performance.json()["id"])

        certificate = client.post(
            "/api/master-data/certificates",
            json={
                "certificate_name": "质量管理体系认证证书",
                "certificate_type": "ISO",
                "certificate_no": "ISO-001",
                "holder_name": "REDACTED",
                "valid_to": "2026-06-30",
            },
        )
        assert certificate.status_code == 201
        certificate_id = UUID(certificate.json()["id"])

        statement = client.post(
            "/api/master-data/financial-statements",
            json={
                "fiscal_year": 2024,
                "statement_type": "annual_report",
                "statement_data": {"assets": 1000, "liabilities": 500},
                "source_note": "2024年财务会计报表",
            },
        )
        assert statement.status_code == 201
        statement_id = UUID(statement.json()["id"])

        duplicate_statement = client.post(
            "/api/master-data/financial-statements",
            json={
                "fiscal_year": 2024,
                "statement_type": "annual_report",
                "statement_data": {"assets": 2000},
            },
        )
        assert duplicate_statement.status_code == 409

        updated_person = client.put(
            f"/api/master-data/people/{person_id}",
            json={"title": "工程师"},
        )
        assert updated_person.status_code == 200
        assert updated_person.json()["title"] == "工程师"

        deleted_certificate = client.delete(f"/api/master-data/certificates/{certificate_id}")
        assert deleted_certificate.status_code == 200
        assert deleted_certificate.json()["deleted"] is True

        deleted_statement = client.delete(f"/api/master-data/financial-statements/{statement_id}")
        assert deleted_statement.status_code == 200

        deleted_performance = client.delete(f"/api/master-data/performances/{performance_id}")
        assert deleted_performance.status_code == 200

        deleted_person = client.delete(f"/api/master-data/people/{person_id}")
        assert deleted_person.status_code == 200

        deleted_company = client.delete(f"/api/master-data/company-profiles/{company_id}")
        assert deleted_company.status_code == 200
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_master_data_tables(conn)
