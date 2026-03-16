"""phase 1 supplementary tables — 9 new tables + project columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Extend project table ---
    op.execute("""
    ALTER TABLE project
      ADD COLUMN IF NOT EXISTS owner_name TEXT,
      ADD COLUMN IF NOT EXISTS tender_no TEXT,
      ADD COLUMN IF NOT EXISTS project_type VARCHAR(64),
      ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'draft',
      ADD COLUMN IF NOT EXISTS tender_deadline TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS created_by VARCHAR(100),
      ADD COLUMN IF NOT EXISTS priority VARCHAR(16) NOT NULL DEFAULT 'normal',
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)

    # --- document_outline_node ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS document_outline_node (
      id UUID PRIMARY KEY,
      document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
      parent_id UUID REFERENCES document_outline_node(id) ON DELETE CASCADE,
      node_type VARCHAR(32) NOT NULL,
      node_no VARCHAR(64),
      title TEXT,
      level INT NOT NULL,
      page_start INT,
      page_end INT,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- standard ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS standard (
      id UUID PRIMARY KEY,
      standard_code VARCHAR(100) NOT NULL,
      standard_name TEXT NOT NULL,
      version_year VARCHAR(20),
      status VARCHAR(32) NOT NULL DEFAULT 'effective',
      specialty VARCHAR(64),
      document_id UUID REFERENCES document(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- standard_clause ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS standard_clause (
      id UUID PRIMARY KEY,
      standard_id UUID NOT NULL REFERENCES standard(id) ON DELETE CASCADE,
      parent_id UUID REFERENCES standard_clause(id) ON DELETE CASCADE,
      clause_no VARCHAR(100),
      clause_title TEXT,
      clause_text TEXT NOT NULL,
      summary TEXT,
      tags JSONB NOT NULL DEFAULT '[]'::jsonb,
      page_start INT,
      page_end INT,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- project_outline_node ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS project_outline_node (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      parent_id UUID REFERENCES project_outline_node(id) ON DELETE CASCADE,
      section_name TEXT NOT NULL,
      level INT NOT NULL,
      sort_order INT NOT NULL DEFAULT 0,
      required BOOLEAN NOT NULL DEFAULT TRUE,
      human_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- human_confirmation ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS human_confirmation (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      confirm_type VARCHAR(64) NOT NULL,
      target_id UUID,
      confirmed BOOLEAN NOT NULL DEFAULT FALSE,
      confirmed_by VARCHAR(100),
      confirmed_at TIMESTAMPTZ,
      note TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- section_template ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS section_template (
      id UUID PRIMARY KEY,
      template_name TEXT NOT NULL,
      project_type VARCHAR(64),
      section_name TEXT NOT NULL,
      template_text TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- workflow_run ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS workflow_run (
      id UUID PRIMARY KEY,
      workflow_name VARCHAR(100) NOT NULL,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      state VARCHAR(32) NOT NULL DEFAULT 'pending',
      current_step VARCHAR(100),
      context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      trace_id VARCHAR(100) NOT NULL,
      error_message TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- workflow_step_log ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS workflow_step_log (
      id UUID PRIMARY KEY,
      workflow_run_id UUID NOT NULL REFERENCES workflow_run(id) ON DELETE CASCADE,
      step_name VARCHAR(100) NOT NULL,
      state VARCHAR(32) NOT NULL,
      started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      finished_at TIMESTAMPTZ,
      message TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- scoring_criteria (B-02: 评分标准结构化) ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS scoring_criteria (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      dimension TEXT NOT NULL,
      max_score NUMERIC(6,2) NOT NULL,
      scoring_method TEXT,
      source_document_id UUID REFERENCES document(id) ON DELETE SET NULL,
      source_page INT,
      human_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
      confirmed_by VARCHAR(100),
      confirmed_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scoring_criteria;")
    op.execute("DROP TABLE IF EXISTS workflow_step_log;")
    op.execute("DROP TABLE IF EXISTS workflow_run;")
    op.execute("DROP TABLE IF EXISTS section_template;")
    op.execute("DROP TABLE IF EXISTS human_confirmation;")
    op.execute("DROP TABLE IF EXISTS project_outline_node;")
    op.execute("DROP TABLE IF EXISTS standard_clause;")
    op.execute("DROP TABLE IF EXISTS standard;")
    op.execute("DROP TABLE IF EXISTS document_outline_node;")
    op.execute("""
    ALTER TABLE project
      DROP COLUMN IF EXISTS owner_name,
      DROP COLUMN IF EXISTS tender_no,
      DROP COLUMN IF EXISTS project_type,
      DROP COLUMN IF EXISTS status,
      DROP COLUMN IF EXISTS tender_deadline,
      DROP COLUMN IF EXISTS created_by,
      DROP COLUMN IF EXISTS priority,
      DROP COLUMN IF EXISTS updated_at;
    """)
