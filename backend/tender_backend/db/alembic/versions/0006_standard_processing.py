"""standard processing columns and sentinel project

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- standard: processing lifecycle columns
    op.execute("""
    ALTER TABLE standard
      ADD COLUMN IF NOT EXISTS processing_status VARCHAR(32) NOT NULL DEFAULT 'pending',
      ADD COLUMN IF NOT EXISTS error_message TEXT,
      ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS processing_finished_at TIMESTAMPTZ;
    """)

    # -- standard_clause: clause type and commentary linkage
    op.execute("""
    ALTER TABLE standard_clause
      ADD COLUMN IF NOT EXISTS clause_type VARCHAR(20) NOT NULL DEFAULT 'normative',
      ADD COLUMN IF NOT EXISTS commentary_clause_id UUID REFERENCES standard_clause(id) ON DELETE SET NULL;
    """)

    # -- sentinel project for standard uploads (not tied to a tender project)
    op.execute("""
    INSERT INTO project (id, name)
    VALUES ('00000000-0000-0000-0000-000000000001', '规范规程资料库')
    ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE standard_clause DROP COLUMN IF EXISTS commentary_clause_id;")
    op.execute("ALTER TABLE standard_clause DROP COLUMN IF EXISTS clause_type;")
    op.execute("ALTER TABLE standard DROP COLUMN IF EXISTS processing_finished_at;")
    op.execute("ALTER TABLE standard DROP COLUMN IF EXISTS processing_started_at;")
    op.execute("ALTER TABLE standard DROP COLUMN IF EXISTS error_message;")
    op.execute("ALTER TABLE standard DROP COLUMN IF EXISTS processing_status;")
