"""review issue template routing

Revision ID: 0052
Revises: 0051
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS issue_source TEXT;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS template_chapter_id UUID NULL REFERENCES project_template_chapter(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS template_block_id UUID NULL REFERENCES project_template_block(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS suggested_workspace TEXT;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS requirement_response_id UUID NULL REFERENCES project_requirement_response(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS seal_block_id UUID NULL REFERENCES project_template_block(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS source_clarification_id UUID NULL REFERENCES tender_clarification(id) ON DELETE SET NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_review_issue_workspace ON review_issue(project_id, suggested_workspace, issue_source);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_review_issue_workspace;")
    for column in ["source_clarification_id", "seal_block_id", "requirement_response_id", "suggested_workspace", "template_block_id", "template_chapter_id", "issue_source"]:
        op.execute(f"ALTER TABLE review_issue DROP COLUMN IF EXISTS {column};")
