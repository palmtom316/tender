"""evidence asset master data

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS evidence_asset (
      id UUID PRIMARY KEY,
      owner_type TEXT NOT NULL,
      owner_id UUID,
      asset_name TEXT NOT NULL,
      asset_type TEXT NOT NULL DEFAULT 'supporting_document',
      file_name TEXT NOT NULL,
      file_path TEXT NOT NULL,
      media_type TEXT,
      issuer_name TEXT,
      issued_on DATE,
      expires_on DATE,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evidence_asset;")
