"""tender summary

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tender_summary (
          project_id UUID PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
          tender_document_id UUID NULL REFERENCES tender_document(id) ON DELETE SET NULL,
          project_name TEXT,
          tenderer TEXT,
          tender_agency TEXT,
          project_location TEXT,
          construction_period TEXT,
          quality_requirement TEXT,
          control_price TEXT,
          bid_bond TEXT,
          bid_open_time TEXT,
          bid_deadline TEXT,
          raw_facts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_chunk_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          extracted_model TEXT,
          extracted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tender_summary_document "
        "ON tender_summary (tender_document_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tender_summary_document;")
    op.execute("DROP TABLE IF EXISTS tender_summary;")
