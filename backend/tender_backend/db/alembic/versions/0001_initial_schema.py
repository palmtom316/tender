"""initial schema — 13 base tables

Revision ID: 0001
Revises: None
Create Date: 2026-03-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS project (
      id UUID PRIMARY KEY,
      name TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS project_file (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      filename TEXT NOT NULL,
      content_type TEXT NOT NULL,
      size_bytes BIGINT NOT NULL,
      storage_key TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS document (
      id UUID PRIMARY KEY,
      project_file_id UUID NOT NULL REFERENCES project_file(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS parse_job (
      id UUID PRIMARY KEY,
      document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
      status TEXT NOT NULL,
      provider TEXT NOT NULL,
      provider_job_id TEXT NULL,
      error TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS document_section (
      id UUID PRIMARY KEY,
      document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
      section_code TEXT NULL,
      title TEXT NOT NULL,
      level INT NOT NULL DEFAULT 1,
      page_start INT NULL,
      page_end INT NULL,
      text TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS document_table (
      id UUID PRIMARY KEY,
      document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
      section_id UUID NULL REFERENCES document_section(id) ON DELETE SET NULL,
      page INT NULL,
      raw_json JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS document_table_override (
      id UUID PRIMARY KEY,
      document_table_id UUID NOT NULL REFERENCES document_table(id) ON DELETE CASCADE,
      override_json JSONB NOT NULL,
      created_by TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS project_requirement (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      category TEXT NOT NULL,
      title TEXT NOT NULL,
      requirement_text TEXT NULL,
      source_text TEXT NULL,
      source_file TEXT NULL,
      source_locator TEXT NULL,
      confidence DOUBLE PRECISION NULL,
      is_veto BOOLEAN NOT NULL DEFAULT false,
      is_hard_constraint BOOLEAN NOT NULL DEFAULT false,
      requires_human_confirm BOOLEAN NOT NULL DEFAULT false,
      ignored_for_pricing BOOLEAN NOT NULL DEFAULT false,
      applies_to_chapter TEXT NULL,
      review_status TEXT NOT NULL DEFAULT 'pending',
      review_note TEXT NULL,
      source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
      human_confirmed BOOLEAN NOT NULL DEFAULT false,
      confirmed_by TEXT NULL,
      confirmed_at TIMESTAMPTZ NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS project_fact (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      fact_key TEXT NOT NULL,
      fact_value TEXT NOT NULL,
      source_text TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS requirement_match (
      id UUID PRIMARY KEY,
      requirement_id UUID NOT NULL REFERENCES project_requirement(id) ON DELETE CASCADE,
      match_status TEXT NOT NULL,
      matched_source_type TEXT,
      matched_source_id UUID,
      matched_title TEXT,
      match_score DOUBLE PRECISION,
      evidence_summary TEXT,
      missing_reason TEXT,
      requires_human_confirm BOOLEAN NOT NULL DEFAULT false,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

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

    op.execute("""
    CREATE TABLE IF NOT EXISTS chapter_draft (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      chapter_code TEXT NOT NULL,
      content_md TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS review_issue (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      severity TEXT NOT NULL,
      title TEXT NOT NULL,
      detail TEXT NULL,
      resolved BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS export_record (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      status TEXT NOT NULL,
      template_name TEXT NULL,
      export_key TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS synonym_dictionary (
      id UUID PRIMARY KEY,
      term TEXT NOT NULL,
      synonyms TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS synonym_dictionary;")
    op.execute("DROP TABLE IF EXISTS export_record;")
    op.execute("DROP TABLE IF EXISTS review_issue;")
    op.execute("DROP TABLE IF EXISTS chapter_draft;")
    op.execute("DROP TABLE IF EXISTS bid_chapter_requirement;")
    op.execute("DROP TABLE IF EXISTS bid_chapter;")
    op.execute("DROP TABLE IF EXISTS bid_outline;")
    op.execute("DROP TABLE IF EXISTS requirement_match;")
    op.execute("DROP TABLE IF EXISTS project_fact;")
    op.execute("DROP TABLE IF EXISTS project_requirement;")
    op.execute("DROP TABLE IF EXISTS document_table_override;")
    op.execute("DROP TABLE IF EXISTS document_table;")
    op.execute("DROP TABLE IF EXISTS document_section;")
    op.execute("DROP TABLE IF EXISTS parse_job;")
    op.execute("DROP TABLE IF EXISTS document;")
    op.execute("DROP TABLE IF EXISTS project_file;")
    op.execute("DROP TABLE IF EXISTS project;")
