"""review issue links and delivery package tables

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS chapter_code TEXT NULL;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS requirement_id UUID NULL REFERENCES project_requirement(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_delivery_package (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      version_no INT NOT NULL,
      status TEXT NOT NULL DEFAULT 'created',
      package_name TEXT NOT NULL,
      package_path TEXT NOT NULL,
      docx_path TEXT NULL,
      doc_path TEXT NULL,
      review_report_path TEXT NULL,
      response_matrix_path TEXT NULL,
      missing_items_path TEXT NULL,
      traceability_path TEXT NULL,
      confirmation_record_path TEXT NULL,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_by TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (project_id, version_no)
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_delivery_package_project ON bid_delivery_package (project_id, created_at DESC);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_bid_delivery_package_project;")
    op.execute("DROP TABLE IF EXISTS bid_delivery_package;")
    op.execute("ALTER TABLE review_issue DROP COLUMN IF EXISTS metadata_json;")
    op.execute("ALTER TABLE review_issue DROP COLUMN IF EXISTS requirement_id;")
    op.execute("ALTER TABLE review_issue DROP COLUMN IF EXISTS chapter_code;")
