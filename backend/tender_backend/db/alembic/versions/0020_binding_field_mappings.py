"""binding field mappings

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE bid_template_binding_rule
      ADD COLUMN IF NOT EXISTS field_mappings JSONB NOT NULL DEFAULT '[]'::jsonb;
    """)
    op.execute("""
    ALTER TABLE bid_template_binding_rule
      ADD COLUMN IF NOT EXISTS field_mapping_mode VARCHAR(16) NOT NULL DEFAULT 'augment';
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE bid_template_binding_rule
      DROP COLUMN IF EXISTS field_mapping_mode;
    """)
    op.execute("""
    ALTER TABLE bid_template_binding_rule
      DROP COLUMN IF EXISTS field_mappings;
    """)
