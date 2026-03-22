"""track clause source metadata

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE standard_clause
      ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'text',
      ADD COLUMN IF NOT EXISTS source_label TEXT;
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_standard_clause_source_type
      ON standard_clause (standard_id, source_type);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_standard_clause_source_type;")
    op.execute("ALTER TABLE standard_clause DROP COLUMN IF EXISTS source_label;")
    op.execute("ALTER TABLE standard_clause DROP COLUMN IF EXISTS source_type;")
