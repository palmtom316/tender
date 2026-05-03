"""project requirement extraction method

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 'keyword' = rule-based pre-extraction (extract_requirements_from_source_chunks)
    # 'ai'      = AI-only extraction (no matching keyword candidate)
    # 'merged'  = AI extraction merged into a prior keyword candidate
    op.execute(
        "ALTER TABLE project_requirement "
        "ADD COLUMN IF NOT EXISTS extraction_method TEXT NOT NULL DEFAULT 'keyword';"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_requirement_extraction_method "
        "ON project_requirement (project_id, extraction_method);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_requirement_extraction_method;")
    op.execute("ALTER TABLE project_requirement DROP COLUMN IF EXISTS extraction_method;")
