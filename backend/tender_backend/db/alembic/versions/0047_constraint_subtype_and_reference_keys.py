"""constraint subtype and chart reference keys

Revision ID: 0047
Revises: 0046
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE tender_constraint_item ADD COLUMN IF NOT EXISTS constraint_subtype TEXT;")
    op.execute("""
    UPDATE tender_constraint_item
    SET constraint_subtype = metadata_json->>'constraint_subtype'
    WHERE constraint_subtype IS NULL
      AND metadata_json ? 'constraint_subtype';
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_tender_constraint_item_subtype
      ON tender_constraint_item(project_id, constraint_subtype, status)
      WHERE constraint_subtype IS NOT NULL;
    """)
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS referenced_chart_keys TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];")
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_chapter_draft_referenced_chart_keys
      ON chapter_draft USING GIN (referenced_chart_keys);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chapter_draft_referenced_chart_keys;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS referenced_chart_keys;")
    op.execute("DROP INDEX IF EXISTS idx_tender_constraint_item_subtype;")
    op.execute("ALTER TABLE tender_constraint_item DROP COLUMN IF EXISTS constraint_subtype;")
    op.execute("ALTER TABLE project DROP COLUMN IF EXISTS metadata_json;")
