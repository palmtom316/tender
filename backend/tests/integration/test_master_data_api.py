from __future__ import annotations

import csv
import os
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from tender_backend.core.config import get_settings
from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


_AUTH_HEADERS = {"Authorization": "Bearer dev-token"}


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _apply_master_data_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_initial_schema_sql())
    conn.execute("""
    CREATE TABLE IF NOT EXISTS app_user (
      id UUID PRIMARY KEY,
      username VARCHAR(50) NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      display_name VARCHAR(100) NOT NULL,
      role VARCHAR(20) NOT NULL DEFAULT 'editor',
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS user_session (
      token VARCHAR(64) PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days'
    );

    CREATE TABLE IF NOT EXISTS library_company (
      id UUID PRIMARY KEY,
      company_key TEXT NOT NULL UNIQUE,
      company_name TEXT NOT NULL,
      company_type TEXT,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS company_profile (
      id UUID PRIMARY KEY,
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
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
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
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
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
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
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
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
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
      fiscal_year INT NOT NULL,
      statement_type TEXT NOT NULL,
      statement_data JSONB NOT NULL DEFAULT '{}'::jsonb,
      source_note TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (fiscal_year, statement_type)
    );

    CREATE TABLE IF NOT EXISTS evidence_asset (
      id UUID PRIMARY KEY,
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
      owner_type TEXT NOT NULL,
      owner_id UUID,
      asset_name TEXT NOT NULL,
      asset_domain VARCHAR(64) NOT NULL DEFAULT 'generic',
      asset_category VARCHAR(64) NOT NULL DEFAULT 'supporting_document',
      asset_type TEXT NOT NULL DEFAULT 'supporting_document',
      file_name TEXT NOT NULL,
      file_path TEXT NOT NULL,
      media_type TEXT,
      issuer_name TEXT,
      issued_on DATE,
      expires_on DATE,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    conn.execute("""
    ALTER TABLE company_profile
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    ALTER TABLE person_profile
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    ALTER TABLE project_performance
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    ALTER TABLE qualification_certificate
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    ALTER TABLE financial_statement
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    ALTER TABLE evidence_asset
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    ALTER TABLE evidence_asset
      ADD COLUMN IF NOT EXISTS asset_domain VARCHAR(64) NOT NULL DEFAULT 'generic';
    ALTER TABLE evidence_asset
      ADD COLUMN IF NOT EXISTS asset_category VARCHAR(64) NOT NULL DEFAULT 'supporting_document';
    """)
    conn.commit()


def _reset_master_data_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM evidence_asset;")
    conn.execute("DELETE FROM financial_statement;")
    conn.execute("DELETE FROM qualification_certificate;")
    conn.execute("DELETE FROM project_performance;")
    conn.execute("DELETE FROM person_profile;")
    conn.execute("DELETE FROM company_profile;")
    conn.execute("DELETE FROM library_company;")
    conn.execute("DELETE FROM user_session;")
    conn.execute("DELETE FROM app_user;")
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_master_data_crud_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    upload_root = Path.cwd() / "tmp" / "test_master_data_uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVIDENCE_UPLOAD_DIR", str(upload_root))
    get_settings.cache_clear()

    with psycopg.connect(db_url) as conn:
        _apply_master_data_schema(conn)
        _reset_master_data_tables(conn)

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
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

        managed_asset = upload_root / "iso-001.pdf"
        managed_asset.write_bytes(b"%PDF-1.7\n")
        evidence = client.post(
            "/api/master-data/evidence-assets",
            json={
                "owner_type": "qualification_certificate",
                "owner_id": str(certificate_id),
                "asset_name": "质量认证扫描件",
                "file_name": "iso-001.pdf",
                "file_path": str(managed_asset),
                "asset_type": "certificate_scan",
                "sort_order": 1,
            },
        )
        assert evidence.status_code == 201
        evidence_id = UUID(evidence.json()["id"])
        assert "file_path" not in evidence.json()

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

        evidence_list = client.get("/api/master-data/evidence-assets")
        assert evidence_list.status_code == 200
        assert any(UUID(row["id"]) == evidence_id for row in evidence_list.json())
        assert all("file_path" not in row for row in evidence_list.json())

        updated_evidence = client.put(
            f"/api/master-data/evidence-assets/{evidence_id}",
            json={"issuer_name": "中国质量认证中心"},
        )
        assert updated_evidence.status_code == 200
        assert updated_evidence.json()["issuer_name"] == "中国质量认证中心"

        updated_person = client.put(
            f"/api/master-data/people/{person_id}",
            json={"title": "工程师"},
        )
        assert updated_person.status_code == 200
        assert updated_person.json()["title"] == "工程师"

        deleted_evidence = client.delete(f"/api/master-data/evidence-assets/{evidence_id}")
        assert deleted_evidence.status_code == 200

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

        anon_client = SyncASGIClient(app)
        unauthorized = anon_client.get("/api/master-data/company-profiles")
        assert unauthorized.status_code == 401
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_master_data_tables(conn)


def test_login_session_token_can_access_protected_master_data(monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    upload_root = Path.cwd() / "tmp" / "test_master_data_uploads_session"
    upload_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVIDENCE_UPLOAD_DIR", str(upload_root))
    get_settings.cache_clear()

    with psycopg.connect(db_url) as conn:
        _apply_master_data_schema(conn)
        _reset_master_data_tables(conn)

    client = SyncASGIClient(app)
    try:
        created_user = client.post(
            "/api/users",
            json={
                "username": "editor01",
                "password": "secret123",
                "display_name": "Editor 01",
                "role": "editor",
            },
        )
        assert created_user.status_code == 201

        login = client.post(
            "/api/auth/login",
            json={"username": "editor01", "password": "secret123"},
        )
        assert login.status_code == 200
        token = login.json()["token"]

        session_client = SyncASGIClient(app)
        session_client.headers.update({"Authorization": f"Bearer {token}"})
        protected = session_client.get("/api/master-data/company-profiles")
        assert protected.status_code == 200
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_master_data_tables(conn)


def test_company_contract_performance_export_excludes_pdf_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    upload_root = Path.cwd() / "tmp" / "test_master_data_contract_export"
    upload_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVIDENCE_UPLOAD_DIR", str(upload_root))
    get_settings.cache_clear()

    with psycopg.connect(db_url) as conn:
        _apply_master_data_schema(conn)
        _reset_master_data_tables(conn)

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        library = client.post(
            "/api/master-data/library-companies",
            json={"company_name": "REDACTED", "company_type": "施工总承包"},
        )
        assert library.status_code == 201
        library_id = library.json()["id"]

        created = client.post(
            "/api/master-data/company-contract-performances",
            json={
                "library_company_id": library_id,
                "contract_name": "配网建设项目合同",
                "party_a_company": "REDACTED",
                "contract_category": "施工合同",
                "engineering_category": "配网工程",
                "contract_amount": 1200000,
                "contract_signed_date": "2025-01-08",
                "contract_completed_date": "2025-12-20",
                "contract_status": "履约中",
                "signature_asset_name": "合同主要签署页面.pdf",
                "invoice_asset_name": "合同发票.pdf",
                "invoice_verification_asset_name": "合同发票验证.pdf",
                "performance_evaluation_asset_name": "合同履约评价.pdf",
            },
        )
        assert created.status_code == 201

        exported = client.get(f"/api/master-data/company-contract-performances/export?library_company_id={library_id}")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/csv")
        content = exported.text.lstrip("\ufeff")
        rows = list(csv.reader(content.splitlines()))
        assert rows[0] == [
            "自动编号",
            "合同名称",
            "合同甲方单位",
            "合同类别",
            "工程类别",
            "合同金额",
            "合同签订日期",
            "合同竣工日期",
            "合同状态",
        ]
        assert "合同主要签署页面" not in rows[0]
        assert "合同发票" not in rows[0]
        assert "合同发票验证" not in rows[0]
        assert "合同履约评价" not in rows[0]
        assert rows[1][1] == "配网建设项目合同"
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_master_data_tables(conn)


def test_company_contract_performance_update_and_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    upload_root = Path.cwd() / "tmp" / "test_master_data_contract_update"
    upload_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVIDENCE_UPLOAD_DIR", str(upload_root))
    get_settings.cache_clear()

    with psycopg.connect(db_url) as conn:
        _apply_master_data_schema(conn)
        _reset_master_data_tables(conn)

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        library = client.post(
            "/api/master-data/library-companies",
            json={"company_name": "REDACTED", "company_type": "施工总承包"},
        )
        assert library.status_code == 201
        library_id = library.json()["id"]

        created = client.post(
            "/api/master-data/company-contract-performances",
            json={
                "library_company_id": library_id,
                "contract_name": "配网建设项目合同",
                "party_a_company": "REDACTED",
                "contract_category": "施工合同",
                "engineering_category": "配网工程",
                "contract_amount": 1200000,
                "contract_signed_date": "2025-01-08",
                "contract_completed_date": "2025-12-20",
                "contract_status": "履约中",
            },
        )
        assert created.status_code == 201
        performance_id = created.json()["id"]

        updated = client.put(
            f"/api/master-data/company-contract-performances/{performance_id}",
            json={
                "contract_name": "配网建设项目合同-更新",
                "contract_amount": 1300000,
                "contract_status": "已完工",
                "invoice_asset_name": "合同发票.pdf",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["contract_name"] == "配网建设项目合同-更新"
        assert updated.json()["contract_status"] == "已完工"
        assert updated.json()["invoice_asset_name"] == "合同发票.pdf"

        deleted = client.delete(f"/api/master-data/company-contract-performances/{performance_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True

        listed = client.get(f"/api/master-data/company-contract-performances?library_company_id={library_id}")
        assert listed.status_code == 200
        assert listed.json() == []
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_master_data_tables(conn)
