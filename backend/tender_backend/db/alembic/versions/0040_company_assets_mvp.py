"""company assets MVP

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS company_asset (
      id UUID PRIMARY KEY,
      library_company_id UUID NOT NULL REFERENCES library_company(id) ON DELETE CASCADE,
      asset_type TEXT NOT NULL CHECK (asset_type IN ('vehicle','machine','tool','safety')),
      name TEXT NOT NULL,
      spec_model TEXT,
      serial_no TEXT,
      manufacturer TEXT,
      quantity NUMERIC(12,2) NOT NULL DEFAULT 1,
      unit TEXT NOT NULL,
      ownership TEXT NOT NULL CHECK (ownership IN ('self','leased','third_party')),
      acquired_at DATE,
      expires_at DATE,
      technical_condition TEXT,
      status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','maintenance','retired')),
      location TEXT,
      extras JSONB NOT NULL DEFAULT '{}'::jsonb,
      notes TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_asset_lib_type ON company_asset(library_company_id, asset_type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_asset_expires ON company_asset(expires_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_asset_status ON company_asset(status);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS company_asset_attachment (
      id UUID PRIMARY KEY,
      asset_id UUID NOT NULL REFERENCES company_asset(id) ON DELETE CASCADE,
      evidence_asset_id UUID NOT NULL REFERENCES evidence_asset(id) ON DELETE CASCADE,
      attachment_kind TEXT NOT NULL DEFAULT 'general',
      effective_at DATE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_asset_attachment_asset ON company_asset_attachment(asset_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_asset_attachment_evidence ON company_asset_attachment(evidence_asset_id);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS project_equipment_selection (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      asset_id UUID NOT NULL REFERENCES company_asset(id) ON DELETE RESTRICT,
      asset_type TEXT NOT NULL,
      intended_role TEXT,
      snapshot_json JSONB,
      display_order INT NOT NULL DEFAULT 0,
      confirmed BOOLEAN NOT NULL DEFAULT FALSE,
      confirmed_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_pes_project ON project_equipment_selection(project_id, asset_type, display_order);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_pes_project_asset ON project_equipment_selection(project_id, asset_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_pes_project_asset;")
    op.execute("DROP INDEX IF EXISTS idx_pes_project;")
    op.execute("DROP TABLE IF EXISTS project_equipment_selection;")
    op.execute("DROP INDEX IF EXISTS idx_company_asset_attachment_evidence;")
    op.execute("DROP INDEX IF EXISTS idx_company_asset_attachment_asset;")
    op.execute("DROP TABLE IF EXISTS company_asset_attachment;")
    op.execute("DROP INDEX IF EXISTS idx_company_asset_status;")
    op.execute("DROP INDEX IF EXISTS idx_company_asset_expires;")
    op.execute("DROP INDEX IF EXISTS idx_company_asset_lib_type;")
    op.execute("DROP TABLE IF EXISTS company_asset;")
