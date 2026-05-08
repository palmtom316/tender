"""project personnel selection

Revision ID: 0041
Revises: 0040
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS project_personnel_selection (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      person_id UUID NOT NULL REFERENCES person_profile(id) ON DELETE RESTRICT,
      intended_role TEXT,
      snapshot_json JSONB,
      display_order INT NOT NULL DEFAULT 0,
      confirmed BOOLEAN NOT NULL DEFAULT FALSE,
      confirmed_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_pps_project ON project_personnel_selection(project_id, display_order, created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pps_person ON project_personnel_selection(person_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_pps_project_person ON project_personnel_selection(project_id, person_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_pps_project_person;")
    op.execute("DROP INDEX IF EXISTS idx_pps_person;")
    op.execute("DROP INDEX IF EXISTS idx_pps_project;")
    op.execute("DROP TABLE IF EXISTS project_personnel_selection;")
