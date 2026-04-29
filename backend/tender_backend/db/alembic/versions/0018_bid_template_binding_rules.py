"""bid template binding rules

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_template_binding_rule (
      id UUID PRIMARY KEY,
      template_item_id UUID NOT NULL REFERENCES bid_template_item(id) ON DELETE CASCADE,
      binding_name TEXT NOT NULL,
      source_type VARCHAR(64) NOT NULL,
      selection_mode VARCHAR(32) NOT NULL DEFAULT 'all',
      source_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
      output_key TEXT NOT NULL,
      required BOOLEAN NOT NULL DEFAULT TRUE,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (template_item_id, binding_name)
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bid_template_binding_rule;")
