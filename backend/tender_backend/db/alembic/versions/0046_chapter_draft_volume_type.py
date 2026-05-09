"""scope chapter drafts by volume

Revision ID: 0046
Revises: 0045
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS volume_type TEXT;")
    op.execute("""
    UPDATE chapter_draft cd
    SET volume_type = bc.volume_type
    FROM bid_chapter bc
    WHERE cd.project_id = bc.project_id
      AND cd.chapter_code = bc.chapter_code
      AND cd.volume_type IS NULL;
    """)
    op.execute("UPDATE chapter_draft SET volume_type = 'technical' WHERE volume_type IS NULL;")
    op.execute("ALTER TABLE chapter_draft ALTER COLUMN volume_type SET NOT NULL;")
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_chapter_draft_project_volume_code
      ON chapter_draft(project_id, volume_type, chapter_code);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_chapter_draft_project_volume_code;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS volume_type;")
