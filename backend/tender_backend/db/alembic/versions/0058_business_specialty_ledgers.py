"""business specialty ledgers

Revision ID: 0058
Revises: 0057
Create Date: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS business_specialty_ledger (
      id UUID PRIMARY KEY,
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
      company_key TEXT,
      ledger_type TEXT NOT NULL CHECK (
        ledger_type IN (
          'bank_account',
          'bid_bond',
          'green_certificate',
          'technology_achievement',
          'esg_report',
          'award'
        )
      ),
      year INT,
      evidence_asset_id UUID REFERENCES evidence_asset(id) ON DELETE SET NULL,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK (library_company_id IS NOT NULL OR company_key IS NOT NULL)
    );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_business_specialty_ledger_company "
        "ON business_specialty_ledger(library_company_id, ledger_type, year);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_business_specialty_ledger_company_key "
        "ON business_specialty_ledger(company_key, ledger_type, year);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_business_specialty_ledger_metadata "
        "ON business_specialty_ledger USING GIN (metadata_json);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_business_specialty_ledger_metadata;")
    op.execute("DROP INDEX IF EXISTS idx_business_specialty_ledger_company_key;")
    op.execute("DROP INDEX IF EXISTS idx_business_specialty_ledger_company;")
    op.execute("DROP TABLE IF EXISTS business_specialty_ledger;")
