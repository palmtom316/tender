"""bid workflow redesign backbone

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS industry TEXT NOT NULL DEFAULT 'power';")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS business_line TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS sub_type TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS employer_name TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS employer_type TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS evaluation_method TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS evaluation_detail JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS qualification_review_type TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS submission_deadline TIMESTAMPTZ;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS bid_opening_time TIMESTAMPTZ;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS bid_validity_period INT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS bid_bond_amount TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS bid_bond_form TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS bid_bond_deadline TIMESTAMPTZ;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS voltage_level TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS project_scope TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS is_live_work_required BOOLEAN NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS controlled_price TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS is_subcontract_allowed BOOLEAN NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS is_consortium_allowed BOOLEAN NOT NULL DEFAULT false;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS tender_platform TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS submission_target TEXT NOT NULL DEFAULT 'local_zip';")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS platform_file_rules JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS procurement_type TEXT NOT NULL DEFAULT 'single';")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS parent_project_id UUID NULL REFERENCES project(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS section_name TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS lot_name TEXT;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS selected_template_package_id UUID NULL REFERENCES bid_template_package(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE project ADD COLUMN IF NOT EXISTS workflow_status TEXT NOT NULL DEFAULT 'created';")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_workflow_status ON project (workflow_status, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_parent ON project (parent_project_id);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_workflow_event (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      previous_status TEXT,
      next_status TEXT NOT NULL,
      actor TEXT,
      reason TEXT,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_workflow_event_project ON bid_workflow_event (project_id, created_at DESC);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_volume (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      bid_outline_id UUID NULL REFERENCES bid_outline(id) ON DELETE CASCADE,
      volume_type TEXT NOT NULL,
      title TEXT NOT NULL,
      strategy TEXT NOT NULL DEFAULT 'generated',
      status TEXT NOT NULL DEFAULT 'draft',
      sort_order INT NOT NULL DEFAULT 0,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (bid_outline_id, volume_type)
    );
    """)
    op.execute("ALTER TABLE bid_chapter ADD COLUMN IF NOT EXISTS volume_id UUID NULL REFERENCES bid_volume(id) ON DELETE SET NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_volume_project ON bid_volume (project_id, sort_order);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_chapter_volume ON bid_chapter (volume_id, sort_order);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS tender_constraint_set (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      version INT NOT NULL DEFAULT 1,
      status TEXT NOT NULL DEFAULT 'draft',
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (project_id, version)
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS tender_constraint_item (
      id UUID PRIMARY KEY,
      constraint_set_id UUID NOT NULL REFERENCES tender_constraint_set(id) ON DELETE CASCADE,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      requirement_id UUID NULL REFERENCES project_requirement(id) ON DELETE SET NULL,
      category TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'draft',
      confirmation_level TEXT NOT NULL DEFAULT 'auto_accept',
      title TEXT NOT NULL,
      constraint_text TEXT NOT NULL DEFAULT '',
      source_file TEXT,
      source_locator TEXT,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tender_constraint_item_project ON tender_constraint_item (project_id, category, status);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS tender_clarification (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      round_no INT NOT NULL DEFAULT 1,
      clarification_type TEXT NOT NULL DEFAULT 'clarification',
      title TEXT NOT NULL,
      source_file TEXT,
      content_text TEXT NOT NULL DEFAULT '',
      impact_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tender_clarification_project ON tender_clarification (project_id, round_no);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS external_bid_attachment (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      volume_type TEXT NOT NULL DEFAULT 'pricing',
      attachment_type TEXT NOT NULL DEFAULT 'external_pricing',
      filename TEXT NOT NULL,
      file_path TEXT,
      content_type TEXT,
      size_bytes BIGINT,
      status TEXT NOT NULL DEFAULT 'attached',
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_bid_attachment_project ON external_bid_attachment (project_id, volume_type);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS compliance_check_run (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'completed',
      summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_by TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS compliance_check_finding (
      id UUID PRIMARY KEY,
      run_id UUID NOT NULL REFERENCES compliance_check_run(id) ON DELETE CASCADE,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      severity TEXT NOT NULL,
      rule_code TEXT NOT NULL,
      title TEXT NOT NULL,
      detail TEXT NOT NULL DEFAULT '',
      requirement_id UUID NULL REFERENCES project_requirement(id) ON DELETE SET NULL,
      status TEXT NOT NULL DEFAULT 'open',
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_compliance_check_finding_project ON compliance_check_finding (project_id, severity, status);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS post_bid_review (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      bid_result TEXT NOT NULL DEFAULT 'unknown',
      ranking INT,
      score NUMERIC,
      price_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
      competitor_notes TEXT,
      win_loss_reasons TEXT,
      reusable_lessons TEXT,
      opening_record_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      clarification_json JSONB NOT NULL DEFAULT '[]'::jsonb,
      notice_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      contract_status TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_post_bid_review_project ON post_bid_review (project_id, created_at DESC);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_post_bid_review_project;")
    op.execute("DROP TABLE IF EXISTS post_bid_review;")
    op.execute("DROP INDEX IF EXISTS idx_compliance_check_finding_project;")
    op.execute("DROP TABLE IF EXISTS compliance_check_finding;")
    op.execute("DROP TABLE IF EXISTS compliance_check_run;")
    op.execute("DROP INDEX IF EXISTS idx_external_bid_attachment_project;")
    op.execute("DROP TABLE IF EXISTS external_bid_attachment;")
    op.execute("DROP INDEX IF EXISTS idx_tender_clarification_project;")
    op.execute("DROP TABLE IF EXISTS tender_clarification;")
    op.execute("DROP INDEX IF EXISTS idx_tender_constraint_item_project;")
    op.execute("DROP TABLE IF EXISTS tender_constraint_item;")
    op.execute("DROP TABLE IF EXISTS tender_constraint_set;")
    op.execute("DROP INDEX IF EXISTS idx_bid_chapter_volume;")
    op.execute("DROP INDEX IF EXISTS idx_bid_volume_project;")
    op.execute("ALTER TABLE bid_chapter DROP COLUMN IF EXISTS volume_id;")
    op.execute("DROP TABLE IF EXISTS bid_volume;")
    op.execute("DROP INDEX IF EXISTS idx_bid_workflow_event_project;")
    op.execute("DROP TABLE IF EXISTS bid_workflow_event;")
    op.execute("DROP INDEX IF EXISTS idx_project_parent;")
    op.execute("DROP INDEX IF EXISTS idx_project_workflow_status;")
    for column in [
        "workflow_status", "selected_template_package_id", "lot_name", "section_name", "parent_project_id",
        "procurement_type", "platform_file_rules", "submission_target", "tender_platform",
        "is_consortium_allowed", "is_subcontract_allowed", "controlled_price", "is_live_work_required",
        "project_scope", "voltage_level", "bid_bond_deadline", "bid_bond_form", "bid_bond_amount",
        "bid_validity_period", "bid_opening_time", "submission_deadline", "qualification_review_type",
        "evaluation_detail", "evaluation_method", "employer_type", "employer_name", "sub_type", "business_line", "industry",
    ]:
        op.execute(f"ALTER TABLE project DROP COLUMN IF EXISTS {column};")
