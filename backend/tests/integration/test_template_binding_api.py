from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import fitz  # PyMuPDF
import psycopg
import pytest
from docx import Document

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
      field_mappings JSONB NOT NULL DEFAULT '[]'::jsonb,
      field_mapping_mode VARCHAR(16) NOT NULL DEFAULT 'augment',
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
    CREATE TABLE IF NOT EXISTS evidence_asset (
      id UUID PRIMARY KEY,
      owner_type TEXT NOT NULL,
      owner_id UUID,
      asset_name TEXT NOT NULL,
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
    ALTER TABLE bid_template_binding_rule
      ADD COLUMN IF NOT EXISTS field_mappings JSONB NOT NULL DEFAULT '[]'::jsonb;
    """)
    conn.execute("""
    ALTER TABLE bid_template_binding_rule
      ADD COLUMN IF NOT EXISTS field_mapping_mode VARCHAR(16) NOT NULL DEFAULT 'augment';
    """)
    conn.commit()


def _reset_schema(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM bid_template_binding_rule;")
    conn.execute("DELETE FROM bid_template_item;")
    conn.execute("DELETE FROM bid_template_package;")
    conn.execute("DELETE FROM evidence_asset;")
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
    (source_dir / "7.1.资质证书证明材料.docx").write_bytes(b"docx")

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
        evidence_item_id = UUID(package["items"][2]["id"])

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
        certificate = client.post(
            "/api/master-data/certificates",
            json={
                "certificate_name": "质量管理体系认证证书",
                "holder_name": "REDACTED",
                "certificate_no": "ISO-001",
            },
        )
        assert certificate.status_code == 201
        certificate_id = UUID(certificate.json()["id"])
        attachment_file = tmp_path / "quality-cert.pdf"
        pdf = fitz.open()
        page = pdf.new_page(width=595, height=842)
        page.insert_text((72, 72), "Quality Certificate", fontsize=24)
        pdf.save(attachment_file)
        pdf.close()
        evidence_asset = client.post(
            "/api/master-data/evidence-assets",
            json={
                "owner_type": "qualification_certificate",
                "owner_id": str(certificate_id),
                "asset_name": "质量认证证书扫描件",
                "asset_type": "certificate_scan",
                "file_name": "quality-cert.pdf",
                "file_path": str(attachment_file),
            },
        )
        assert evidence_asset.status_code == 201

        binding1 = client.post(
            f"/api/template-items/{basic_item_id}/bindings",
            json={
                "binding_name": "company_basic",
                "source_type": "company_profile",
                "selection_mode": "latest",
                "field_mappings": [
                    {"target_field": "company_title", "source_field": "company_name"},
                    {"target_field": "contact_summary", "source_fields": ["contact_name", "contact_phone"], "transform": "join", "join_with": " / "},
                ],
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
        binding3 = client.post(
            f"/api/template-items/{evidence_item_id}/bindings",
            json={
                "binding_name": "certificate_assets",
                "source_type": "evidence_asset",
                "selection_mode": "all",
                "output_key": "assets",
                "source_filters": {
                    "equals": {"owner_type": "qualification_certificate"},
                    "record_ids": [evidence_asset.json()["id"]],
                },
            },
        )
        assert binding3.status_code == 201

        preview = client.get(f"/api/template-packages/{package_id}/context-preview")
        assert preview.status_code == 200
        body = preview.json()
        assert body["items"][0]["bindings"][0]["data"]["company_name"] == "REDACTED"
        assert body["items"][0]["bindings"][0]["data"]["company_title"] == "REDACTED"
        assert body["items"][0]["bindings"][0]["data"]["contact_summary"] == "王莉莉"
        assert body["items"][1]["bindings"][0]["matched_count"] == 1
        assert body["items"][2]["bindings"][0]["matched_count"] == 1

        item_render = client.get(f"/api/template-items/{basic_item_id}/render-context")
        assert item_render.status_code == 200
        assert item_render.json()["ready"] is True
        assert item_render.json()["context"]["company"]["company_name"] == "REDACTED"
        assert item_render.json()["context"]["company"]["company_title"] == "REDACTED"
        assert item_render.json()["bindings"][0]["field_mapping_mode"] == "augment"

        package_render = client.get(f"/api/template-packages/{package_id}/render-context")
        assert package_render.status_code == 200
        assert package_render.json()["ready_item_count"] == 3
        assert package_render.json()["total_item_count"] == 3

        rendered = client.post(f"/api/template-items/{basic_item_id}/render-docx")
        assert rendered.status_code == 200
        assert rendered.json()["ready"] is True
        assert rendered.json()["output_path"].endswith(".docx")

        bundle = client.post(
            f"/api/template-packages/{package_id}/render-bundle",
            json={"include_zip": False},
        )
        assert bundle.status_code == 200
        bundle_body = bundle.json()
        assert bundle_body["rendered_count"] == 3
        assert bundle_body["failed_count"] == 0
        assert Path(bundle_body["output_dir"]).exists()
        assert bundle_body["items"][0]["output_path"].endswith(".docx")
        assert Path(bundle_body["items"][0]["output_path"]).exists()
        assert bundle_body["zip_path"] is None
        evidence_outputs = [item for item in bundle_body["items"] if item["item_id"] == str(evidence_item_id)]
        assert len(evidence_outputs) == 1
        assert evidence_outputs[0]["copied_asset_count"] == 1
        assert evidence_outputs[0]["embedded_preview_count"] == 1
        evidence_manifest = Path(evidence_outputs[0]["output_path"])
        assert evidence_manifest.exists()
        assert (evidence_manifest.parent / f"{evidence_manifest.stem}_attachments" / "quality-cert.pdf").exists()
        embedded_doc = Document(str(evidence_manifest))
        assert embedded_doc.paragraphs[0].text == "（一）资质证书证明材料"
        assert len(embedded_doc.inline_shapes) >= 1

        zipped_bundle = client.post(
            f"/api/template-packages/{package_id}/render-bundle",
            json={"include_zip": True},
        )
        assert zipped_bundle.status_code == 200
        zipped_body = zipped_bundle.json()
        assert zipped_body["zip_path"] is not None
        assert zipped_body["zip_path"].endswith(".zip")
        assert Path(zipped_body["zip_path"]).exists()

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
