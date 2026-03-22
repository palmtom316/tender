"""preserve standard parse assets

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE document
      ADD COLUMN IF NOT EXISTS parser_name TEXT,
      ADD COLUMN IF NOT EXISTS parser_version TEXT,
      ADD COLUMN IF NOT EXISTS raw_payload JSONB;
    """)

    op.execute("""
    ALTER TABLE document_section
      ADD COLUMN IF NOT EXISTS raw_json JSONB,
      ADD COLUMN IF NOT EXISTS text_source VARCHAR(32),
      ADD COLUMN IF NOT EXISTS sort_order INT NOT NULL DEFAULT 0;
    """)

    op.execute("""
    ALTER TABLE document_table
      ADD COLUMN IF NOT EXISTS page_start INT,
      ADD COLUMN IF NOT EXISTS page_end INT,
      ADD COLUMN IF NOT EXISTS table_title TEXT,
      ADD COLUMN IF NOT EXISTS table_html TEXT;
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_document_section_document_sort
      ON document_section (document_id, sort_order, created_at);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_section_document_sort;")
    op.execute("ALTER TABLE document_table DROP COLUMN IF EXISTS table_html;")
    op.execute("ALTER TABLE document_table DROP COLUMN IF EXISTS table_title;")
    op.execute("ALTER TABLE document_table DROP COLUMN IF EXISTS page_end;")
    op.execute("ALTER TABLE document_table DROP COLUMN IF EXISTS page_start;")
    op.execute("ALTER TABLE document_section DROP COLUMN IF EXISTS sort_order;")
    op.execute("ALTER TABLE document_section DROP COLUMN IF EXISTS text_source;")
    op.execute("ALTER TABLE document_section DROP COLUMN IF EXISTS raw_json;")
    op.execute("ALTER TABLE document DROP COLUMN IF EXISTS raw_payload;")
    op.execute("ALTER TABLE document DROP COLUMN IF EXISTS parser_version;")
    op.execute("ALTER TABLE document DROP COLUMN IF EXISTS parser_name;")
