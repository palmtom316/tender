"""project template instances

Revision ID: 0051
Revises: 0050
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_template_instance (
          id UUID PRIMARY KEY,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          base_template_package_id UUID NULL REFERENCES bid_template_package(id) ON DELETE SET NULL,
          category_code VARCHAR(64) NOT NULL,
          display_name TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'draft',
          version INT NOT NULL DEFAULT 1,
          confirmed_at TIMESTAMPTZ NULL,
          confirmed_by TEXT NULL,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_project_template_instance_current ON project_template_instance(project_id) WHERE status <> 'superseded';")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_instance_project ON project_template_instance(project_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_instance_base ON project_template_instance(base_template_package_id);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_template_chapter (
          id UUID PRIMARY KEY,
          template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          parent_id UUID NULL REFERENCES project_template_chapter(id) ON DELETE CASCADE,
          source_template_item_id UUID NULL REFERENCES bid_template_item(id) ON DELETE SET NULL,
          chapter_code TEXT NOT NULL,
          chapter_title TEXT NOT NULL,
          volume_type TEXT NOT NULL,
          sort_order INT NOT NULL DEFAULT 0,
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          chapter_status TEXT NOT NULL DEFAULT 'draft',
          tender_requirement_status TEXT NOT NULL DEFAULT 'not_checked',
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          lock_owner TEXT NULL,
          locked_until TIMESTAMPTZ NULL,
          lock_version INT NOT NULL DEFAULT 1,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_chapter_instance ON project_template_chapter(template_instance_id, parent_id, sort_order);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_chapter_project ON project_template_chapter(project_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_chapter_source ON project_template_chapter(source_template_item_id);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_template_block (
          id UUID PRIMARY KEY,
          template_chapter_id UUID NOT NULL REFERENCES project_template_chapter(id) ON DELETE CASCADE,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          block_type TEXT NOT NULL,
          sort_order INT NOT NULL DEFAULT 0,
          label TEXT NOT NULL,
          content_text TEXT NOT NULL DEFAULT '',
          prompt_text TEXT NOT NULL DEFAULT '',
          placeholder_key TEXT NULL,
          asset_type TEXT NULL,
          required BOOLEAN NOT NULL DEFAULT FALSE,
          render_options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          condition_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_block_chapter ON project_template_block(template_chapter_id, sort_order);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_block_project ON project_template_block(project_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_block_type ON project_template_block(block_type);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_requirement_response (
          id UUID PRIMARY KEY,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE,
          requirement_id UUID NOT NULL REFERENCES project_requirement(id) ON DELETE CASCADE,
          template_chapter_id UUID NULL REFERENCES project_template_chapter(id) ON DELETE SET NULL,
          template_block_id UUID NULL REFERENCES project_template_block(id) ON DELETE SET NULL,
          response_status TEXT NOT NULL DEFAULT 'unanswered',
          response_text TEXT NOT NULL DEFAULT '',
          deviation_note TEXT NOT NULL DEFAULT '',
          source_type TEXT NOT NULL DEFAULT 'tender_requirement',
          source_clarification_id UUID NULL REFERENCES tender_clarification(id) ON DELETE SET NULL,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (template_instance_id, requirement_id)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_requirement_response_project ON project_requirement_response(project_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_requirement_response_instance ON project_requirement_response(template_instance_id, response_status);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_template_seal_confirmation (
          id UUID PRIMARY KEY,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE,
          seal_block_id UUID NOT NULL REFERENCES project_template_block(id) ON DELETE CASCADE,
          confirmation_status TEXT NOT NULL DEFAULT 'pending',
          confirmed_by TEXT NULL,
          confirmed_at TIMESTAMPTZ NULL,
          note TEXT NOT NULL DEFAULT '',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (template_instance_id, seal_block_id)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_seal_instance ON project_template_seal_confirmation(template_instance_id, confirmation_status);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_template_revision (
          id UUID PRIMARY KEY,
          template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          revision_no INT NOT NULL,
          change_type TEXT NOT NULL,
          change_summary TEXT NOT NULL,
          snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_by TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (template_instance_id, revision_no)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_template_revision_instance ON project_template_revision(template_instance_id, revision_no DESC);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS template_promotion_proposal (
          id UUID PRIMARY KEY,
          template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE,
          base_template_package_id UUID NULL REFERENCES bid_template_package(id) ON DELETE SET NULL,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          proposal_status TEXT NOT NULL DEFAULT 'draft',
          diff_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_by TEXT NULL,
          reviewed_by TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          reviewed_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_template_promotion_proposal_instance ON template_promotion_proposal(template_instance_id, proposal_status);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS template_promotion_proposal;")
    op.execute("DROP TABLE IF EXISTS project_template_revision;")
    op.execute("DROP TABLE IF EXISTS project_template_seal_confirmation;")
    op.execute("DROP TABLE IF EXISTS project_requirement_response;")
    op.execute("DROP TABLE IF EXISTS project_template_block;")
    op.execute("DROP TABLE IF EXISTS project_template_chapter;")
    op.execute("DROP TABLE IF EXISTS project_template_instance;")
