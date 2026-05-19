"""add rendered artifact fields to chapter drafts

Revision ID: 0057
Revises: 0056
Create Date: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS rendered_docx_path TEXT;")
    op.execute(
        "ALTER TABLE chapter_draft "
        "ADD COLUMN IF NOT EXISTS rendered_artifact_json JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS rendered_artifact_json;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS rendered_docx_path;")
