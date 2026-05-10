"""tender remediation indexes and legacy flags

Revision ID: 0048
Revises: 0047
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_tender_constraint_set_project_status_version
      ON tender_constraint_set(project_id, status, version DESC);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_tender_constraint_item_set_status_subtype
      ON tender_constraint_item(constraint_set_id, status, constraint_subtype);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_bid_outline_project_status_stale
      ON bid_outline(project_id, status, is_stale, updated_at DESC);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_chapter_draft_project_stale_updated
      ON chapter_draft(project_id, is_stale, updated_at DESC);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_chart_asset_project_placeholder_status
      ON chart_asset(project_id, placeholder_key, status)
      WHERE placeholder_key IS NOT NULL;
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_bid_chapter_template_conflict_policy
      ON bid_chapter USING GIN ((metadata_json -> 'template_conflict'));
    """)
    op.execute("""
    UPDATE project p
    SET metadata_json = jsonb_set(
      COALESCE(p.metadata_json, '{}'::jsonb),
      '{legacy_pre_constraint_set}',
      'true'::jsonb,
      true
    )
    WHERE NOT EXISTS (
      SELECT 1 FROM tender_constraint_set tcs WHERE tcs.project_id = p.id
    )
      AND (
        EXISTS (SELECT 1 FROM chapter_draft cd WHERE cd.project_id = p.id)
        OR EXISTS (SELECT 1 FROM bid_outline bo WHERE bo.project_id = p.id)
      );
    """)
    op.execute("""
    UPDATE chart_asset
    SET placeholder_key = chart_type
    WHERE placeholder_key IS NULL
      AND chart_type IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_bid_chapter_template_conflict_policy;")
    op.execute("DROP INDEX IF EXISTS idx_chart_asset_project_placeholder_status;")
    op.execute("DROP INDEX IF EXISTS idx_chapter_draft_project_stale_updated;")
    op.execute("DROP INDEX IF EXISTS idx_bid_outline_project_status_stale;")
    op.execute("DROP INDEX IF EXISTS idx_tender_constraint_item_set_status_subtype;")
    op.execute("DROP INDEX IF EXISTS idx_tender_constraint_set_project_status_version;")
