"""tender source chunks

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS source_chunk (
      id UUID PRIMARY KEY,
      tender_document_id UUID NOT NULL REFERENCES tender_document(id) ON DELETE CASCADE,
      tender_document_file_id UUID NOT NULL REFERENCES tender_document_file(id) ON DELETE CASCADE,
      chunk_type VARCHAR(32) NOT NULL,
      source_file TEXT NOT NULL,
      document_type TEXT,
      section_title TEXT,
      source_locator TEXT NOT NULL,
      title TEXT,
      text TEXT,
      table_json JSONB,
      page_start INT,
      page_end INT,
      sheet_name TEXT,
      row_start INT,
      row_end INT,
      paragraph_index INT,
      sort_order INT NOT NULL DEFAULT 0,
      confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_source_chunk_document_file_sort
      ON source_chunk (tender_document_id, tender_document_file_id, sort_order);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_source_chunk_type
      ON source_chunk (tender_document_id, chunk_type);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_source_chunk_type;")
    op.execute("DROP INDEX IF EXISTS idx_source_chunk_document_file_sort;")
    op.execute("DROP TABLE IF EXISTS source_chunk;")
