"""project.category_code referencing template_package_category

Revision ID: 0050
Revises: 0049
Create Date: 2026-05-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE project
      ADD COLUMN IF NOT EXISTS category_code VARCHAR(64);
    """)
    op.execute("""
    ALTER TABLE project
      DROP CONSTRAINT IF EXISTS project_category_code_fkey;
    """)
    op.execute("""
    ALTER TABLE project
      ADD CONSTRAINT project_category_code_fkey
      FOREIGN KEY (category_code)
      REFERENCES template_package_category(code)
      ON DELETE SET NULL;
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_category_code ON project (category_code);"
    )
    op.execute("""
    UPDATE project
    SET category_code = sub.code
    FROM (
      SELECT code FROM template_package_category WHERE enabled = TRUE
    ) AS sub
    WHERE project.category_code IS NULL
      AND (
        project.business_line = sub.code
        OR project.project_type = sub.code
        OR project.sub_type = sub.code
      );
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_category_code;")
    op.execute("""
    ALTER TABLE project
      DROP CONSTRAINT IF EXISTS project_category_code_fkey;
    """)
    op.execute("""
    ALTER TABLE project
      DROP COLUMN IF EXISTS category_code;
    """)
