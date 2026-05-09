"""scope bid chapter code uniqueness by volume

Revision ID: 0044
Revises: 0043
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE bid_chapter DROP CONSTRAINT IF EXISTS bid_chapter_bid_outline_id_chapter_code_key;")
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_bid_chapter_outline_volume_code
      ON bid_chapter (bid_outline_id, volume_type, chapter_code);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_bid_chapter_outline_volume_code;")
    op.execute("""
    ALTER TABLE bid_chapter
      ADD CONSTRAINT bid_chapter_bid_outline_id_chapter_code_key
      UNIQUE (bid_outline_id, chapter_code);
    """)
