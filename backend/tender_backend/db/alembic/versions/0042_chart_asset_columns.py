"""chart asset render columns

Revision ID: 0042
Revises: 0041
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE chart_asset ADD COLUMN IF NOT EXISTS placeholder_key TEXT;")
    op.execute("ALTER TABLE chart_asset ADD COLUMN IF NOT EXISTS mermaid_source TEXT;")
    op.execute("ALTER TABLE chart_asset ADD COLUMN IF NOT EXISTS rendered_png_path TEXT;")
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_chart_asset_project_placeholder
      ON chart_asset(project_id, placeholder_key)
      WHERE placeholder_key IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_chart_asset_project_placeholder;")
    op.execute("ALTER TABLE chart_asset DROP COLUMN IF EXISTS rendered_png_path;")
    op.execute("ALTER TABLE chart_asset DROP COLUMN IF EXISTS mermaid_source;")
    op.execute("ALTER TABLE chart_asset DROP COLUMN IF EXISTS placeholder_key;")
