"""separate template stale reasons

Revision ID: 0055
Revises: 0054
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("chapter_draft", "chart_asset"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS template_stale_reason TEXT NULL;")


def downgrade() -> None:
    for table in ("chart_asset", "chapter_draft"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS template_stale_reason;")
