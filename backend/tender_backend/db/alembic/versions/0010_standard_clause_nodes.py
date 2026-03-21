"""structured standard clause nodes

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE standard_clause
      ADD COLUMN IF NOT EXISTS node_type VARCHAR(20) NOT NULL DEFAULT 'clause',
      ADD COLUMN IF NOT EXISTS node_key VARCHAR(255),
      ADD COLUMN IF NOT EXISTS node_label VARCHAR(100);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_standard_clause_node_key
      ON standard_clause (standard_id, node_key);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_standard_clause_node_key;")
    op.execute("ALTER TABLE standard_clause DROP COLUMN IF EXISTS node_label;")
    op.execute("ALTER TABLE standard_clause DROP COLUMN IF EXISTS node_key;")
    op.execute("ALTER TABLE standard_clause DROP COLUMN IF EXISTS node_type;")
