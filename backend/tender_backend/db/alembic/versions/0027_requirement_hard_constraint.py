"""requirement hard constraint flag

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE project_requirement
      ADD COLUMN IF NOT EXISTS is_hard_constraint BOOLEAN NOT NULL DEFAULT false;
    """)
    op.execute("""
    UPDATE project_requirement
    SET is_hard_constraint = true
    WHERE is_veto = true
       OR category IN ('qualification', 'performance', 'project_team', 'format', 'special');
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_project_requirement_project_confirm
      ON project_requirement (project_id, category, human_confirmed, requires_human_confirm);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_requirement_project_confirm;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS is_hard_constraint;")
