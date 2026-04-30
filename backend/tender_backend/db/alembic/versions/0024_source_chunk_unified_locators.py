"""source chunk unified locators

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE source_chunk ADD COLUMN IF NOT EXISTS document_type TEXT;")
    op.execute("ALTER TABLE source_chunk ADD COLUMN IF NOT EXISTS section_title TEXT;")
    op.execute("ALTER TABLE source_chunk ADD COLUMN IF NOT EXISTS page_start INT;")
    op.execute("ALTER TABLE source_chunk ADD COLUMN IF NOT EXISTS page_end INT;")
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_source_chunk_document_page
      ON source_chunk (tender_document_id, page_start, page_end);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_source_chunk_document_page;")
    op.execute("ALTER TABLE source_chunk DROP COLUMN IF EXISTS page_end;")
    op.execute("ALTER TABLE source_chunk DROP COLUMN IF EXISTS page_start;")
    op.execute("ALTER TABLE source_chunk DROP COLUMN IF EXISTS section_title;")
    op.execute("ALTER TABLE source_chunk DROP COLUMN IF EXISTS document_type;")
