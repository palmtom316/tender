"""project membership access control

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-06
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS project_member (
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
      role VARCHAR(20) NOT NULL DEFAULT 'editor',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (project_id, user_id)
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_member_user ON project_member (user_id, project_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_member_user;")
    op.execute("DROP TABLE IF EXISTS project_member;")
