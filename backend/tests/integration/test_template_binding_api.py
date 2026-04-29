from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from tender_backend.core.config import get_settings
from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _apply_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_initial_schema_sql())
    conn.execute("""
    CREATE TABLE IF NOT EXISTS bid_template_package (
      id UUID PRIMARY KEY,
      package_key TEXT NOT NULL UNIQUE,
      display_name TEXT NOT NULL,
      package_type VARCHAR(32) NOT NULL,
      source_root TEXT NOT NULL,
      source_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS bid_template_item (
      id UUID PRIMARY KEY,
      package_id UUID NOT NULL REFERENCES bid_template_package(id) ON DELETE CASCADE,
      item_code TEXT NULL,
      item_name TEXT NOT NULL,
      filename TEXT NOT NULL,
      relative_path TEXT NOT NULL,
      source_kind VARCHAR(16) NOT NULL DEFAULT 'docx',
      item_type VARCHAR(32) NOT NULL DEFAULT 'chapter',
      render_mode VARCHAR(32) NOT NULL DEFAULT 'templated',
      is_required BOOLEAN NOT NULL DEFAULT TRUE,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (package_id, relative_path)
    );
    CREATE TABLE IF NOT EXISTS bid_template_binding_rule (
      id UUID PRIMARY KEY,
      template_item_id UUID NOT NULL REFERENCES bid_template_item(id) ON DELETE CASCADE,
      binding_name TEXT NOT NULL,
      source_type VARCHAR(64) NOT NULL,
      selection_mode VARCHAR(32) NOT NULL DEFAULT 'all',
      source_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
      output_key TEXT NOT NULL,
      required BOOLEAN NOT NULL DEFAULT TRUE,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (template_item_id, binding_name)
    );
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


def _reset_schema(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM bid_template_binding_rule;")
    conn.execute("DELETE FROM bid_template_item;")
    conn.execute("DELETE FROM bid_template_package;")
    conn.execute("DELETE FROM financial_statement;")
    conn.execute("DELETE FROM qualification_certificate;")
    conn.execute("DELETE FROM project_performance;")
    conn.execute("DELETE FROM person_profile;")
    conn.execute("DELETE FROM company_profile;")
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_binding_rule_and_context_preview_flow(tmp_path: Path) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    source_dir = tmp_path / "20258B商务文件"
    source_dir.mkdir()
    (source_dir / "5.1.基本情况表.docx").write_bytes(b"docx")
    (source_dir / "6.1.人员汇总表及人员简历表.docx").write_bytes(b"docx")

    with psycopg.connect(db_url) as conn:
        _apply_schema(conn)
        _reset_schema(conn)

    client = SyncASGIClient(app)
    try:
        imported = client.post("/api/template-packages/import", json={"source_dir": str(source_dir)})
        assert imported.status_code == 200
        package = imported.json()
        package_id = UUID(package["id"])
        basic_item_id = UUID(package["items"][0]["id"])
        people_item_id = UUID(package["items"][1]["id"])

        company = client.post(
            "/api/master-data/company-profiles",
            json={"company_name": "REDACTED", "contact_name": "王莉莉"},
        )
        assert company.status_code == 201
        person = client.post(
            "/api/master-data/people",
            json={"full_name": "唐玮", "role_name": "项目总经理"},
        )
        assert person.status_code == 201

        binding1 = client.post(
            f"/api/template-items/{basic_item_id}/bindings",
            json={
                "binding_name": "company_basic",
                "source_type": "company_profile",
                "selection_mode": "latest",
                "output_key": "company",
            },
        )
        assert binding1.status_code == 201

        binding2 = client.post(
            f"/api/template-items/{people_item_id}/bindings",
            json={
                "binding_name": "team_people",
                "source_type": "person_profile",
                "selection_mode": "all",
                "output_key": "people",
                "source_filters": {"equals": {"role_name": "项目总经理"}},
            },
        )
        assert binding2.status_code == 201
        binding2_id = UUID(binding2.json()["id"])

        preview = client.get(f"/api/template-packages/{package_id}/context-preview")
        assert preview.status_code == 200
        body = preview.json()
        assert body["items"][0]["bindings"][0]["data"]["company_name"] == "REDACTED"
        assert body["items"][1]["bindings"][0]["matched_count"] == 1

        item_render = client.get(f"/api/template-items/{basic_item_id}/render-context")
        assert item_render.status_code == 200
        assert item_render.json()["ready"] is True
        assert item_render.json()["context"]["company"]["company_name"] == "REDACTED"

        package_render = client.get(f"/api/template-packages/{package_id}/render-context")
        assert package_render.status_code == 200
        assert package_render.json()["ready_item_count"] == 2
        assert package_render.json()["total_item_count"] == 2

        updated = client.put(
            f"/api/template-bindings/{binding2_id}",
            json={"selection_mode": "first"},
        )
        assert updated.status_code == 200
        assert updated.json()["selection_mode"] == "first"

        listed = client.get(f"/api/template-items/{people_item_id}/bindings")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        deleted = client.delete(f"/api/template-bindings/{binding2_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_schema(conn)
