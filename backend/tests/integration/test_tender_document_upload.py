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


def _apply_tender_document_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_initial_schema_sql())
    conn.execute("""
    CREATE TABLE IF NOT EXISTS tender_document (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      original_filename TEXT NOT NULL,
      upload_type VARCHAR(16) NOT NULL,
      status VARCHAR(32) NOT NULL,
      content_type TEXT NOT NULL,
      size_bytes BIGINT NOT NULL,
      storage_key TEXT NOT NULL,
      file_sha256 TEXT NOT NULL,
      error TEXT NULL,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS tender_document_file (
      id UUID PRIMARY KEY,
      tender_document_id UUID NOT NULL REFERENCES tender_document(id) ON DELETE CASCADE,
      parent_file_id UUID NULL REFERENCES tender_document_file(id) ON DELETE CASCADE,
      filename TEXT NOT NULL,
      relative_path TEXT NOT NULL,
      storage_key TEXT NOT NULL,
      content_type TEXT NOT NULL,
      size_bytes BIGINT NOT NULL,
      file_type VARCHAR(32) NOT NULL,
      classification VARCHAR(64) NOT NULL DEFAULT 'unclassified',
      depth INT NOT NULL DEFAULT 0,
      is_archive BOOLEAN NOT NULL DEFAULT FALSE,
      is_parsable BOOLEAN NOT NULL DEFAULT FALSE,
      parse_status VARCHAR(32) NOT NULL DEFAULT 'pending',
      error TEXT NULL,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    conn.commit()


def _reset_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM tender_document_file;")
    conn.execute("DELETE FROM tender_document;")
    conn.execute("DELETE FROM project_file;")
    conn.execute("DELETE FROM project;")
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_upload_real_zip_tender_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    sample = Path(__file__).resolve().parents[3] / "docs" / "国网招标文件" / "包1_完整招标文件_REDACTED.zip"
    if not sample.is_file():
        pytest.skip("real SGCC tender ZIP sample is not available")

    monkeypatch.setenv("TENDER_DOCUMENT_STORAGE_ROOT", str(tmp_path / "tender-documents"))
    get_settings.cache_clear()

    with psycopg.connect(db_url) as conn:
        _apply_tender_document_schema(conn)
        _reset_tables(conn)

    client = SyncASGIClient(app)
    try:
        project_res = client.post("/api/projects", json={"name": "国网包1"})
        assert project_res.status_code == 200
        project_id = UUID(project_res.json()["id"])

        response = client.post(
            f"/api/projects/{project_id}/tender-documents",
            files={"file": (sample.name, sample.read_bytes(), "application/zip")},
        )
        assert response.status_code == 200
        body = response.json()
        tender_document_id = UUID(body["id"])
        assert body["upload_type"] == "zip"
        assert body["status"] == "completed"

        files = body["files"]
        classifications = {row["classification"] for row in files}
        assert "uploaded_package" in classifications
        assert "tender_notice" in classifications
        assert "tender_document" in classifications
        assert "technical_specification" in classifications
        assert "qualification_requirement" in classifications
        assert "technical_scoring" in classifications
        assert "bid_submission_requirement" in classifications
        assert any(row["filename"].endswith(".docx") and row["is_parsable"] for row in files)
        assert any(row["filename"].endswith(".xlsx") and row["is_parsable"] for row in files)

        listed = client.get(f"/api/projects/{project_id}/tender-documents")
        assert listed.status_code == 200
        assert any(UUID(row["id"]) == tender_document_id for row in listed.json())

        file_list = client.get(f"/api/tender-documents/{tender_document_id}/files")
        assert file_list.status_code == 200
        assert len(file_list.json()) == len(files)
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_tables(conn)


def test_upload_pdf_tender_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    monkeypatch.setenv("TENDER_DOCUMENT_STORAGE_ROOT", str(tmp_path / "tender-documents"))
    get_settings.cache_clear()

    with psycopg.connect(db_url) as conn:
        _apply_tender_document_schema(conn)
        _reset_tables(conn)

    client = SyncASGIClient(app)
    try:
        project_res = client.post("/api/projects", json={"name": "PDF 招标文件"})
        assert project_res.status_code == 200
        project_id = UUID(project_res.json()["id"])

        response = client.post(
            f"/api/projects/{project_id}/tender-documents",
            files={"file": ("招标文件.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["upload_type"] == "pdf"
        assert body["status"] == "uploaded"
        assert len(body["files"]) == 1
        assert body["files"][0]["classification"] == "uploaded_pdf"
        assert body["files"][0]["is_parsable"] is True
    finally:
        client.close()
        with psycopg.connect(db_url) as conn:
            _reset_tables(conn)
