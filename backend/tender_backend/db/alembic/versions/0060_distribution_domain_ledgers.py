"""distribution domain ledgers

Revision ID: 0060
Revises: 0059
Create Date: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0060"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS distribution_domain_ledger (
      id UUID PRIMARY KEY,
      project_id UUID REFERENCES project(id) ON DELETE CASCADE,
      company_key TEXT,
      ledger_type TEXT NOT NULL CHECK (
        ledger_type IN ('outage_window', 'live_work_plan', 'distribution_automation')
      ),
      evidence_asset_id UUID REFERENCES evidence_asset(id) ON DELETE SET NULL,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK (project_id IS NOT NULL OR company_key IS NOT NULL)
    );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_distribution_domain_ledger_project "
        "ON distribution_domain_ledger(project_id, ledger_type, updated_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_distribution_domain_ledger_company "
        "ON distribution_domain_ledger(company_key, ledger_type, updated_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_distribution_domain_ledger_metadata "
        "ON distribution_domain_ledger USING GIN (metadata_json);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_distribution_domain_ledger_metadata;")
    op.execute("DROP INDEX IF EXISTS idx_distribution_domain_ledger_company;")
    op.execute("DROP INDEX IF EXISTS idx_distribution_domain_ledger_project;")
    op.execute("DROP TABLE IF EXISTS distribution_domain_ledger;")
