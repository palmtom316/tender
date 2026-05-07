"""clarification stale impact markers

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS stale_reason TEXT;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS stale_by_clarification_id UUID NULL REFERENCES tender_clarification(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS superseded_by_requirement_id UUID NULL REFERENCES project_requirement(id) ON DELETE SET NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_requirement_stale ON project_requirement (project_id, is_stale, review_status);")

    op.execute("ALTER TABLE bid_outline ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE bid_outline ADD COLUMN IF NOT EXISTS stale_reason TEXT;")
    op.execute("ALTER TABLE bid_outline ADD COLUMN IF NOT EXISTS stale_by_clarification_id UUID NULL REFERENCES tender_clarification(id) ON DELETE SET NULL;")

    op.execute("ALTER TABLE bid_chapter ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE bid_chapter ADD COLUMN IF NOT EXISTS stale_reason TEXT;")
    op.execute("ALTER TABLE bid_chapter ADD COLUMN IF NOT EXISTS stale_by_clarification_id UUID NULL REFERENCES tender_clarification(id) ON DELETE SET NULL;")

    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS stale_reason TEXT;")
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS stale_by_clarification_id UUID NULL REFERENCES tender_clarification(id) ON DELETE SET NULL;")


def downgrade() -> None:
    for table in ["chapter_draft", "bid_chapter", "bid_outline"]:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS stale_by_clarification_id;")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS stale_reason;")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS is_stale;")
    op.execute("DROP INDEX IF EXISTS idx_project_requirement_stale;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS superseded_by_requirement_id;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS stale_by_clarification_id;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS stale_reason;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS is_stale;")
