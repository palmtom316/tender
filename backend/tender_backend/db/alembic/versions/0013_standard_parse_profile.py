"""track per-standard parse profile

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE standard
      ADD COLUMN IF NOT EXISTS parse_profile VARCHAR(32) NOT NULL DEFAULT 'cn_gb';
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_standard_parse_profile
      ON standard (parse_profile);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_standard_parse_profile;")
    op.execute("ALTER TABLE standard DROP COLUMN IF EXISTS parse_profile;")
