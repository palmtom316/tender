"""bid outline chapter planning

Revision ID: 0029
Revises: 0028
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_outline (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      outline_name TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'draft',
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_chapter (
      id UUID PRIMARY KEY,
      bid_outline_id UUID NOT NULL REFERENCES bid_outline(id) ON DELETE CASCADE,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      parent_id UUID NULL REFERENCES bid_chapter(id) ON DELETE CASCADE,
      chapter_code TEXT NOT NULL,
      chapter_title TEXT NOT NULL,
      volume_type TEXT NOT NULL,
      sort_order INT NOT NULL DEFAULT 0,
      outline_md TEXT NOT NULL DEFAULT '',
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (bid_outline_id, chapter_code)
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_chapter_requirement (
      id UUID PRIMARY KEY,
      bid_chapter_id UUID NOT NULL REFERENCES bid_chapter(id) ON DELETE CASCADE,
      requirement_id UUID NOT NULL REFERENCES project_requirement(id) ON DELETE CASCADE,
      mapping_reason TEXT NULL,
      priority_level TEXT NOT NULL DEFAULT 'normal',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (bid_chapter_id, requirement_id)
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_outline_project ON bid_outline (project_id, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_chapter_project ON bid_chapter (project_id, volume_type, sort_order);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_chapter_requirement_requirement ON bid_chapter_requirement (requirement_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_bid_chapter_requirement_requirement;")
    op.execute("DROP INDEX IF EXISTS idx_bid_chapter_project;")
    op.execute("DROP INDEX IF EXISTS idx_bid_outline_project;")
    op.execute("DROP TABLE IF EXISTS bid_chapter_requirement;")
    op.execute("DROP TABLE IF EXISTS bid_chapter;")
    op.execute("DROP TABLE IF EXISTS bid_outline;")
