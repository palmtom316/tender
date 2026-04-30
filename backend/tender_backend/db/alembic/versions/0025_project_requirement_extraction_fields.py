"""project requirement extraction fields

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS requirement_text TEXT;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS source_file TEXT;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS source_locator TEXT;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS is_veto BOOLEAN NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS is_hard_constraint BOOLEAN NOT NULL DEFAULT false;")
    op.execute("""
    ALTER TABLE project_requirement
      ADD COLUMN IF NOT EXISTS requires_human_confirm BOOLEAN NOT NULL DEFAULT false;
    """)
    op.execute("""
    ALTER TABLE project_requirement
      ADD COLUMN IF NOT EXISTS ignored_for_pricing BOOLEAN NOT NULL DEFAULT false;
    """)
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS applies_to_chapter TEXT;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'pending';")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS review_note TEXT;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS source_chunk_id UUID NULL REFERENCES source_chunk(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();")
    op.execute("UPDATE project_requirement SET is_veto = true WHERE category = 'veto';")
    op.execute("""
    UPDATE project_requirement
    SET is_hard_constraint = true
    WHERE is_veto = true
       OR category IN ('qualification', 'performance', 'project_team', 'format', 'special');
    """)
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_project_requirement_source_chunk_category
      ON project_requirement (project_id, category, source_chunk_id, source_locator)
      WHERE source_chunk_id IS NOT NULL;
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_project_requirement_project_category_review
      ON project_requirement (project_id, category, review_status);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_requirement_project_category_review;")
    op.execute("DROP INDEX IF EXISTS ux_project_requirement_source_chunk_category;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS updated_at;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS source_metadata;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS source_chunk_id;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS review_note;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS review_status;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS applies_to_chapter;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS ignored_for_pricing;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS requires_human_confirm;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS is_veto;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS is_hard_constraint;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS confidence;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS source_locator;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS source_file;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS requirement_text;")
