"""template edit propagation metadata

Revision ID: 0053
Revises: 0052
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("chapter_draft", "chart_asset"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS template_instance_id UUID NULL REFERENCES project_template_instance(id) ON DELETE SET NULL;")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS template_revision_no INT NULL;")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS is_stale_by_template BOOLEAN NOT NULL DEFAULT false;")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS stale_by_template_revision_no INT NULL;")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS stale_by_template_block_id UUID NULL REFERENCES project_template_block(id) ON DELETE SET NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chapter_draft_template_stale ON chapter_draft(project_id, is_stale_by_template, template_revision_no);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chart_asset_template_stale ON chart_asset(project_id, is_stale_by_template, template_revision_no);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chart_asset_template_stale;")
    op.execute("DROP INDEX IF EXISTS idx_chapter_draft_template_stale;")
    for table in ("chart_asset", "chapter_draft"):
        for column in (
            "stale_by_template_block_id",
            "stale_by_template_revision_no",
            "is_stale_by_template",
            "template_revision_no",
            "template_instance_id",
        ):
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column};")
