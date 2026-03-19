"""standard processing queue table

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
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


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS standard_processing_job;")
