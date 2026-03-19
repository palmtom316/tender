from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from tender_backend.core.config import get_settings
from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.main import app


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _apply_extra_schema(conn: psycopg.Connection) -> None:
    conn.execute("""
    ALTER TABLE project
      ADD COLUMN IF NOT EXISTS owner_name TEXT,
      ADD COLUMN IF NOT EXISTS tender_no TEXT,
      ADD COLUMN IF NOT EXISTS project_type VARCHAR(64),
      ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'draft',
      ADD COLUMN IF NOT EXISTS tender_deadline TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS created_by VARCHAR(100),
      ADD COLUMN IF NOT EXISTS priority VARCHAR(16) NOT NULL DEFAULT 'normal',
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

    CREATE TABLE IF NOT EXISTS standard (
      id UUID PRIMARY KEY,
      standard_code VARCHAR(100) NOT NULL,
      standard_name TEXT NOT NULL,
      version_year VARCHAR(20),
      status VARCHAR(32) NOT NULL DEFAULT 'effective',
      specialty VARCHAR(64),
      document_id UUID REFERENCES document(id) ON DELETE SET NULL,
      processing_status VARCHAR(32) NOT NULL DEFAULT 'pending',
      error_message TEXT,
      processing_started_at TIMESTAMPTZ,
      processing_finished_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS standard_clause (
      id UUID PRIMARY KEY,
      standard_id UUID NOT NULL REFERENCES standard(id) ON DELETE CASCADE,
      parent_id UUID REFERENCES standard_clause(id) ON DELETE CASCADE,
      clause_no VARCHAR(100),
      clause_title TEXT,
      clause_text TEXT NOT NULL,
      summary TEXT,
      tags JSONB NOT NULL DEFAULT '[]'::jsonb,
      page_start INT,
      page_end INT,
      sort_order INT NOT NULL DEFAULT 0,
      clause_type VARCHAR(20) NOT NULL DEFAULT 'normative',
      commentary_clause_id UUID REFERENCES standard_clause(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS standard_processing_job (
      id UUID PRIMARY KEY,
      standard_id UUID NOT NULL UNIQUE REFERENCES standard(id) ON DELETE CASCADE,
      document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
      ocr_status VARCHAR(16) NOT NULL DEFAULT 'queued',
      ocr_error TEXT,
      ocr_started_at TIMESTAMPTZ,
      ocr_finished_at TIMESTAMPTZ,
      ocr_attempts INT NOT NULL DEFAULT 0,
      ai_status VARCHAR(16) NOT NULL DEFAULT 'blocked',
      ai_error TEXT,
      ai_started_at TIMESTAMPTZ,
      ai_finished_at TIMESTAMPTZ,
      ai_attempts INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    INSERT INTO project (id, name)
    VALUES ('00000000-0000-0000-0000-000000000001', '规范规程资料库')
    ON CONFLICT DO NOTHING;
    """)
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    with psycopg.connect(db_url) as conn:
        conn.execute(load_initial_schema_sql())
        _apply_extra_schema(conn)
        conn.execute("DELETE FROM standard_processing_job;")
        conn.execute("DELETE FROM standard_clause;")
        conn.execute("DELETE FROM standard;")
        conn.execute("DELETE FROM document;")
        conn.execute("DELETE FROM project_file;")
        conn.execute(
            "DELETE FROM project WHERE id <> '00000000-0000-0000-0000-000000000001'"
        )
        conn.commit()

    import tender_backend.api.standards as standards_api
    import tender_backend.main as main_module

    monkeypatch.setattr(standards_api, "_UPLOAD_DIR", str(tmp_path))
    scheduler_stub = type("_SchedulerStub", (), {"wake": lambda self: None})()
    monkeypatch.setattr(main_module, "ensure_standard_processing_scheduler_started", lambda: scheduler_stub)
    monkeypatch.setattr(standards_api, "ensure_standard_processing_scheduler_started", lambda: scheduler_stub)

    return TestClient(app)


def test_batch_upload_creates_queue_jobs_and_returns_queue_state(client: TestClient) -> None:
    response = client.post(
        "/api/standards/upload",
        files=[
            ("files", ("a.pdf", b"%PDF-a", "application/pdf")),
            ("files", ("b.pdf", b"%PDF-b", "application/pdf")),
        ],
        data={
            "items_json": json.dumps([
                {"filename": "a.pdf", "standard_code": "GB 1", "standard_name": "规范A"},
                {"filename": "b.pdf", "standard_code": "GB 2", "standard_name": "规范B", "specialty": "结构"},
            ])
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["processing_status"] == "queued_ocr"
    assert body[0]["ocr_status"] == "queued"
    assert body[0]["ai_status"] == "blocked"

    listed = client.get("/api/standards")
    assert listed.status_code == 200
    assert listed.json()[0]["ocr_status"] in {"queued", "running", "completed", "failed"}


def test_batch_upload_rejects_mismatched_file_and_metadata_count(client: TestClient) -> None:
    response = client.post(
        "/api/standards/upload",
        files=[("files", ("a.pdf", b"%PDF-a", "application/pdf"))],
        data={
            "items_json": json.dumps([
                {"filename": "a.pdf", "standard_code": "GB 1", "standard_name": "规范A"},
                {"filename": "b.pdf", "standard_code": "GB 2", "standard_name": "规范B"},
            ])
        },
    )

    assert response.status_code == 400
    assert "count" in response.json()["detail"].lower()


def test_batch_upload_rejects_missing_required_metadata(client: TestClient) -> None:
    response = client.post(
        "/api/standards/upload",
        files=[("files", ("a.pdf", b"%PDF-a", "application/pdf"))],
        data={
            "items_json": json.dumps([
                {"filename": "a.pdf", "standard_code": "", "standard_name": "规范A"},
            ])
        },
    )

    assert response.status_code == 400
    assert "standard_code" in response.json()["detail"]


def test_retry_endpoint_requeues_failed_jobs_with_stage_aware_reset(client: TestClient) -> None:
    db_url = _db_url()
    assert db_url is not None

    with psycopg.connect(db_url) as conn:
        document_id = uuid4()
        standard_id = uuid4()
        conn.execute("INSERT INTO document (id, project_file_id) VALUES (%s, NULL)", (document_id,))
        conn.execute(
            """
            INSERT INTO standard (id, standard_code, standard_name, document_id, processing_status)
            VALUES (%s, 'GB 1', '规范A', %s, 'failed')
            """,
            (standard_id, document_id),
        )
        conn.execute(
            """
            INSERT INTO standard_processing_job (
              id, standard_id, document_id, ocr_status, ai_status, ai_error
            ) VALUES (%s, %s, %s, 'completed', 'failed', 'llm crashed')
            """,
            (uuid4(), standard_id, document_id),
        )
        conn.commit()

    response = client.post(f"/api/standards/{standard_id}/process")

    assert response.status_code == 200
    assert response.json()["processing_status"] == "queued_ai"

    detail = client.get(f"/api/standards/{standard_id}")
    assert detail.status_code == 200
    assert detail.json()["ocr_status"] == "completed"
    assert detail.json()["ai_status"] == "queued"
