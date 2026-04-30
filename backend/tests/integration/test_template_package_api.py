from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from docx import Document

from tender_backend.core.config import get_settings
from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


_AUTH_HEADERS = {"Authorization": "Bearer dev-token"}


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _apply_template_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_initial_schema_sql())
    conn.execute("""
    CREATE TABLE IF NOT EXISTS template_package_category (
      code TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      description TEXT,
      sort_order INT NOT NULL DEFAULT 0,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS bid_template_package (
      id UUID PRIMARY KEY,
      package_key TEXT NOT NULL UNIQUE,
      display_name TEXT NOT NULL,
      package_type VARCHAR(32) NOT NULL,
      category_code TEXT REFERENCES template_package_category(code),
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
    """)
    conn.execute("""
    ALTER TABLE bid_template_package
      ADD COLUMN IF NOT EXISTS category_code TEXT REFERENCES template_package_category(code);
    """)
    conn.commit()


def _reset_template_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM bid_template_item;")
    conn.execute("DELETE FROM bid_template_package;")
    conn.execute("DELETE FROM template_package_category;")
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_import_and_list_template_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    import_root = tmp_path / "imports"
    import_root.mkdir()
    source_dir = import_root / "20258B商务文件"
    source_dir.mkdir()
    template = Document()
    template.add_paragraph("投标人：{{ company.company_name }}")
    template.save(source_dir / "20258B商务文件.docx")
    monkeypatch.setenv("TEMPLATE_IMPORT_ROOTS", str(import_root))
    get_settings.cache_clear()

    with psycopg.connect(db_url) as conn:
        _apply_template_schema(conn)
        _reset_template_tables(conn)

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        response = client.post(
            "/api/template-packages/import",
            json={"source_dir": str(source_dir)},
        )
        assert response.status_code == 200
        body = response.json()
        package_id = UUID(body["id"])
        assert body["package_type"] == "business"
        assert body["item_count"] == 1
        assert body["items"][0]["item_code"] is None
        assert body["items"][0]["item_type"] == "document"
        assert body["items"][0]["render_mode"] == "single_docx"

        listed = client.get("/api/template-packages")
        assert listed.status_code == 200
        assert any(UUID(row["id"]) == package_id for row in listed.json())

        detail = client.get(f"/api/template-packages/{package_id}")
        assert detail.status_code == 200
        assert detail.json()["items"][0]["item_name"] == "20258B商务文件"

        anon_client = SyncASGIClient(app)
        anon_response = anon_client.get("/api/template-packages")
        assert anon_response.status_code == 401
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_template_tables(conn)
