"""add longform generation evidence schema

Revision ID: 0056
Revises: 0055
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CHAPTER_DRAFT_COLUMNS = (
    "target_pages INT",
    "estimated_pages NUMERIC(8,2)",
    "page_estimate_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    "coverage_report_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    "chart_closure_report_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    "generation_rounds INT NOT NULL DEFAULT 1",
)


_CHAPTER_DRAFT_COLUMN_NAMES = (
    "generation_rounds",
    "chart_closure_report_json",
    "coverage_report_json",
    "page_estimate_json",
    "estimated_pages",
    "target_pages",
)


def upgrade() -> None:
    for column in _CHAPTER_DRAFT_COLUMNS:
        op.execute(f"ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS {column};")

    op.execute(
        "ALTER TABLE export_record "
        "ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bid_generation_subsection_run (
          id UUID PRIMARY KEY,
          bid_generation_run_id UUID NULL REFERENCES bid_generation_run(id) ON DELETE CASCADE,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          bid_chapter_id UUID NULL REFERENCES bid_chapter(id) ON DELETE SET NULL,
          chapter_code TEXT NOT NULL,
          subsection_code TEXT NOT NULL,
          subsection_title TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'completed',
          target_pages NUMERIC(8,2),
          estimated_pages NUMERIC(8,2),
          min_chars INT NOT NULL DEFAULT 0,
          actual_chars INT NOT NULL DEFAULT 0,
          continuation_rounds INT NOT NULL DEFAULT 1,
          prompt_hash TEXT NOT NULL,
          provider TEXT,
          model TEXT,
          input_tokens INT NOT NULL DEFAULT 0,
          output_tokens INT NOT NULL DEFAULT 0,
          latency_ms INT NOT NULL DEFAULT 0,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (project_id, chapter_code, subsection_code)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bid_generation_subsection_project "
        "ON bid_generation_subsection_run (project_id, chapter_code, subsection_code);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_bid_generation_subsection_project;")
    op.execute("DROP TABLE IF EXISTS bid_generation_subsection_run;")
    op.execute("ALTER TABLE export_record DROP COLUMN IF EXISTS metadata_json;")
    for column in _CHAPTER_DRAFT_COLUMN_NAMES:
        op.execute(f"ALTER TABLE chapter_draft DROP COLUMN IF EXISTS {column};")
