"""scoring source fields

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE scoring_criteria ADD COLUMN IF NOT EXISTS source_chunk_id UUID NULL REFERENCES source_chunk(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE scoring_criteria ADD COLUMN IF NOT EXISTS source_file TEXT;")
    op.execute("ALTER TABLE scoring_criteria ADD COLUMN IF NOT EXISTS source_locator TEXT;")
    op.execute("ALTER TABLE scoring_criteria ADD COLUMN IF NOT EXISTS sub_items_json JSONB NOT NULL DEFAULT '[]'::jsonb;")
    op.execute("ALTER TABLE scoring_criteria ADD COLUMN IF NOT EXISTS extraction_method TEXT NOT NULL DEFAULT 'rule';")
    op.execute("CREATE INDEX IF NOT EXISTS idx_scoring_criteria_source_chunk ON scoring_criteria (project_id, source_chunk_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_scoring_criteria_source_chunk;")
    op.execute("ALTER TABLE scoring_criteria DROP COLUMN IF EXISTS extraction_method;")
    op.execute("ALTER TABLE scoring_criteria DROP COLUMN IF EXISTS sub_items_json;")
    op.execute("ALTER TABLE scoring_criteria DROP COLUMN IF EXISTS source_locator;")
    op.execute("ALTER TABLE scoring_criteria DROP COLUMN IF EXISTS source_file;")
    op.execute("ALTER TABLE scoring_criteria DROP COLUMN IF EXISTS source_chunk_id;")
