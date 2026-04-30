"""requirement match table

Revision ID: 0028
Revises: 0027
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS requirement_match (
      id UUID PRIMARY KEY,
      requirement_id UUID NOT NULL REFERENCES project_requirement(id) ON DELETE CASCADE,
      match_status TEXT NOT NULL,
      matched_source_type TEXT,
      matched_source_id UUID,
      matched_title TEXT,
      match_score DOUBLE PRECISION,
      evidence_summary TEXT,
      missing_reason TEXT,
      requires_human_confirm BOOLEAN NOT NULL DEFAULT false,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_requirement_match_requirement_status
      ON requirement_match (requirement_id, match_status);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_requirement_match_requirement_status;")
    op.execute("DROP TABLE IF EXISTS requirement_match;")
