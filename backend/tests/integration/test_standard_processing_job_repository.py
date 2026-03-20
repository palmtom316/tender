from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.db.repositories.standard_processing_job_repository import (
    StandardProcessingJobRepository,
)


_STANDARD_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_initial_schema_sql())
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
    """)
    conn.execute(
        """
        INSERT INTO project (id, name)
        VALUES (%s, '规范规程资料库')
        ON CONFLICT DO NOTHING;
        """,
        (_STANDARD_PROJECT_ID,),
    )
    conn.commit()


@pytest.fixture()
def conn() -> psycopg.Connection:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    conn = psycopg.connect(db_url, row_factory=dict_row)
    _ensure_schema(conn)
    conn.execute("DELETE FROM standard_processing_job;")
    conn.execute("DELETE FROM standard;")
    conn.execute("DELETE FROM document;")
    conn.execute("DELETE FROM project_file;")
    conn.execute("DELETE FROM project WHERE id <> %s;", (_STANDARD_PROJECT_ID,))
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def _create_standard(conn: psycopg.Connection, *, code: str) -> tuple[UUID, UUID]:
    project_file_id = uuid4()
    document_id = uuid4()
    standard_id = uuid4()
    conn.execute(
        """
        INSERT INTO project_file (id, project_id, filename, content_type, size_bytes, storage_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (project_file_id, _STANDARD_PROJECT_ID, f"{code}.pdf", "application/pdf", 7, f"standards/{code}.pdf"),
    )
    conn.execute(
        "INSERT INTO document (id, project_file_id) VALUES (%s, %s)",
        (document_id, project_file_id),
    )
    conn.execute(
        """
        INSERT INTO standard (
          id, standard_code, standard_name, document_id, processing_status
        ) VALUES (%s, %s, %s, %s, 'queued_ocr')
        """,
        (standard_id, code, f"{code} name", document_id),
    )
    conn.commit()
    return standard_id, document_id


def test_create_job_starts_in_ocr_queue(conn: psycopg.Connection) -> None:
    repo = StandardProcessingJobRepository()
    standard_id, document_id = _create_standard(conn, code="GB 1")

    job = repo.create(conn, standard_id=standard_id, document_id=document_id)

    assert job.standard_id == standard_id
    assert job.document_id == document_id
    assert job.ocr_status == "queued"
    assert job.ai_status == "blocked"
    assert job.ocr_attempts == 0
    assert job.ai_attempts == 0


def test_claim_next_ocr_job_returns_oldest_queued_job(conn: psycopg.Connection) -> None:
    repo = StandardProcessingJobRepository()
    first_standard_id, first_document_id = _create_standard(conn, code="GB 1")
    second_standard_id, second_document_id = _create_standard(conn, code="GB 2")
    first = repo.create(conn, standard_id=first_standard_id, document_id=first_document_id)
    repo.create(conn, standard_id=second_standard_id, document_id=second_document_id)

    claimed = repo.claim_next_ocr_job(conn)

    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.ocr_status == "running"
    assert claimed.ocr_attempts == 1


def test_claim_next_ai_job_returns_oldest_ready_job(conn: psycopg.Connection) -> None:
    repo = StandardProcessingJobRepository()
    first_standard_id, first_document_id = _create_standard(conn, code="GB 1")
    second_standard_id, second_document_id = _create_standard(conn, code="GB 2")
    first = repo.create(conn, standard_id=first_standard_id, document_id=first_document_id)
    second = repo.create(conn, standard_id=second_standard_id, document_id=second_document_id)
    conn.execute(
        """
        UPDATE standard_processing_job
        SET ocr_status = 'completed', ai_status = 'queued', updated_at = now()
        WHERE id = %s
        """,
        (first.id,),
    )
    conn.execute(
        """
        UPDATE standard_processing_job
        SET ocr_status = 'completed', ai_status = 'queued', updated_at = now()
        WHERE id = %s
        """,
        (second.id,),
    )
    conn.commit()

    claimed = repo.claim_next_ai_job(conn)

    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.ai_status == "running"
    assert claimed.ai_attempts == 1


def test_retry_resets_failed_ocr_job_back_to_ocr_queue(conn: psycopg.Connection) -> None:
    repo = StandardProcessingJobRepository()
    standard_id, document_id = _create_standard(conn, code="GB 1")
    created = repo.create(conn, standard_id=standard_id, document_id=document_id)
    conn.execute(
        """
        UPDATE standard_processing_job
        SET ocr_status = 'failed', ocr_error = 'ocr crashed', ai_status = 'blocked', updated_at = now()
        WHERE id = %s
        """,
        (created.id,),
    )
    conn.commit()

    retried = repo.retry(conn, standard_id=standard_id)

    assert retried.id == created.id
    assert retried.ocr_status == "queued"
    assert retried.ocr_error is None
    assert retried.ai_status == "blocked"


def test_retry_resets_failed_ai_job_without_touching_ocr_completion(conn: psycopg.Connection) -> None:
    repo = StandardProcessingJobRepository()
    standard_id, document_id = _create_standard(conn, code="GB 1")
    created = repo.create(conn, standard_id=standard_id, document_id=document_id)
    conn.execute(
        """
        UPDATE standard_processing_job
        SET ocr_status = 'completed', ai_status = 'failed', ai_error = 'llm crashed', updated_at = now()
        WHERE id = %s
        """,
        (created.id,),
    )
    conn.commit()

    retried = repo.retry(conn, standard_id=standard_id)

    assert retried.id == created.id
    assert retried.ocr_status == "completed"
    assert retried.ai_status == "queued"
    assert retried.ai_error is None
