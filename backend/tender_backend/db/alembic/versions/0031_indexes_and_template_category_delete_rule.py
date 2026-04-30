"""indexes and template category delete rule

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_bid_template_item_package ON bid_template_item (package_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_evidence_asset_library_company ON evidence_asset (library_company_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_evidence_asset_owner ON evidence_asset (owner_type, owner_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_profile_library_company ON company_profile (library_company_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_person_profile_library_company ON person_profile (library_company_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_performance_library_company ON project_performance (library_company_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_qualification_certificate_library_company ON qualification_certificate (library_company_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_financial_statement_library_company ON financial_statement (library_company_id);")

    op.execute("""
    ALTER TABLE bid_template_package
      DROP CONSTRAINT IF EXISTS bid_template_package_category_code_fkey;
    """)
    op.execute("""
    ALTER TABLE bid_template_package
      ADD CONSTRAINT bid_template_package_category_code_fkey
      FOREIGN KEY (category_code)
      REFERENCES template_package_category(code)
      ON DELETE SET NULL;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE bid_template_package
      DROP CONSTRAINT IF EXISTS bid_template_package_category_code_fkey;
    """)
    op.execute("""
    ALTER TABLE bid_template_package
      ADD CONSTRAINT bid_template_package_category_code_fkey
      FOREIGN KEY (category_code)
      REFERENCES template_package_category(code);
    """)

    op.execute("DROP INDEX IF EXISTS idx_financial_statement_library_company;")
    op.execute("DROP INDEX IF EXISTS idx_qualification_certificate_library_company;")
    op.execute("DROP INDEX IF EXISTS idx_project_performance_library_company;")
    op.execute("DROP INDEX IF EXISTS idx_person_profile_library_company;")
    op.execute("DROP INDEX IF EXISTS idx_company_profile_library_company;")
    op.execute("DROP INDEX IF EXISTS idx_evidence_asset_owner;")
    op.execute("DROP INDEX IF EXISTS idx_evidence_asset_library_company;")
    op.execute("DROP INDEX IF EXISTS idx_bid_template_item_package;")
