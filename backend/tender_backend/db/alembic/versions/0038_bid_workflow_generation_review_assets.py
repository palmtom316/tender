"""bid workflow generation, review, and chart assets

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_generation_run (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      bid_outline_id UUID NULL REFERENCES bid_outline(id) ON DELETE SET NULL,
      bid_chapter_id UUID NULL REFERENCES bid_chapter(id) ON DELETE SET NULL,
      volume_type TEXT NOT NULL,
      strategy TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'completed',
      prompt_inputs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      model_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      output_version TEXT,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_by TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_generation_run_project ON bid_generation_run (project_id, volume_type, created_at DESC);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS chart_asset (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      outline_node_id UUID NULL REFERENCES bid_chapter(id) ON DELETE SET NULL,
      chart_type TEXT NOT NULL,
      title TEXT NOT NULL,
      spec_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      rendered_svg TEXT,
      rendered_path TEXT,
      status TEXT NOT NULL DEFAULT 'draft',
      version INT NOT NULL DEFAULT 1,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_chart_asset_project ON chart_asset (project_id, chart_type, created_at DESC);")

    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS lifecycle_status TEXT NOT NULL DEFAULT 'open';")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS user_decision TEXT;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS source_constraint_id UUID NULL REFERENCES tender_constraint_item(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS scoring_item_id UUID NULL REFERENCES scoring_criteria(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS before_version_id TEXT;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS after_version_id TEXT;")
    op.execute("ALTER TABLE review_issue ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;")

    op.execute("ALTER TABLE compliance_check_finding ADD COLUMN IF NOT EXISTS user_decision TEXT;")
    op.execute("ALTER TABLE compliance_check_finding ADD COLUMN IF NOT EXISTS waived_by TEXT;")
    op.execute("ALTER TABLE compliance_check_finding ADD COLUMN IF NOT EXISTS waived_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE compliance_check_finding ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;")


def downgrade() -> None:
    for column in ["closed_at", "waived_at", "waived_by", "user_decision"]:
        op.execute(f"ALTER TABLE compliance_check_finding DROP COLUMN IF EXISTS {column};")
    for column in [
        "closed_at",
        "after_version_id",
        "before_version_id",
        "scoring_item_id",
        "source_constraint_id",
        "user_decision",
        "lifecycle_status",
    ]:
        op.execute(f"ALTER TABLE review_issue DROP COLUMN IF EXISTS {column};")
    op.execute("DROP INDEX IF EXISTS idx_chart_asset_project;")
    op.execute("DROP TABLE IF EXISTS chart_asset;")
    op.execute("DROP INDEX IF EXISTS idx_bid_generation_run_project;")
    op.execute("DROP TABLE IF EXISTS bid_generation_run;")
