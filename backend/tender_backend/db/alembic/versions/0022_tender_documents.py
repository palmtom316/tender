"""tender document uploads and files

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
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
    """)

    op.execute("""
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

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_tender_document_project_created
      ON tender_document (project_id, created_at DESC);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_tender_document_file_document_depth
      ON tender_document_file (tender_document_id, depth, relative_path);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_tender_document_file_classification
      ON tender_document_file (tender_document_id, classification);
    """)
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_tender_document_file_relative_path
      ON tender_document_file (tender_document_id, relative_path);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_tender_document_file_relative_path;")
    op.execute("DROP INDEX IF EXISTS idx_tender_document_file_classification;")
    op.execute("DROP INDEX IF EXISTS idx_tender_document_file_document_depth;")
    op.execute("DROP INDEX IF EXISTS idx_tender_document_project_created;")
    op.execute("DROP TABLE IF EXISTS tender_document_file;")
    op.execute("DROP TABLE IF EXISTS tender_document;")
