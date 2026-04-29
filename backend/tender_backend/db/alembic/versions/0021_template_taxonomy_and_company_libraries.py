"""template taxonomy and company libraries

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS template_package_category (
      code TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      description TEXT,
      sort_order INT NOT NULL DEFAULT 0,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    INSERT INTO template_package_category (code, display_name, description, sort_order)
    VALUES
      ('sgcc_operation', '国网运维工程', '国家电网运维类项目模板', 10),
      ('sgcc_substation', '国网变电工程', '国家电网变电工程类项目模板', 20),
      ('sgcc_10kv', '国网10KV工程', '国家电网10KV工程类项目模板', 30),
      ('sgcc_low_voltage_distribution', '国网低压营配工程', '国家电网低压营配工程类项目模板', 40),
      ('user_operation', '用户运维工程', '用户侧运维工程类项目模板', 50),
      ('user_distribution', '用户配电工程', '用户侧配电工程类项目模板', 60)
    ON CONFLICT (code) DO NOTHING;
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS library_company (
      id UUID PRIMARY KEY,
      company_key TEXT NOT NULL UNIQUE,
      company_name TEXT NOT NULL,
      company_type TEXT,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    ALTER TABLE bid_template_package
      ADD COLUMN IF NOT EXISTS category_code TEXT REFERENCES template_package_category(code);
    """)

    op.execute("""
    ALTER TABLE company_profile
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    """)

    op.execute("""
    ALTER TABLE person_profile
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    """)

    op.execute("""
    ALTER TABLE project_performance
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    """)

    op.execute("""
    ALTER TABLE qualification_certificate
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    """)

    op.execute("""
    ALTER TABLE financial_statement
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    """)

    op.execute("""
    ALTER TABLE evidence_asset
      ADD COLUMN IF NOT EXISTS library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE;
    """)

    op.execute("""
    ALTER TABLE evidence_asset
      ADD COLUMN IF NOT EXISTS asset_domain VARCHAR(64) NOT NULL DEFAULT 'generic';
    """)

    op.execute("""
    ALTER TABLE evidence_asset
      ADD COLUMN IF NOT EXISTS asset_category VARCHAR(64) NOT NULL DEFAULT 'supporting_document';
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE evidence_asset
      DROP COLUMN IF EXISTS asset_category;
    """)
    op.execute("""
    ALTER TABLE evidence_asset
      DROP COLUMN IF EXISTS asset_domain;
    """)
    op.execute("""
    ALTER TABLE evidence_asset
      DROP COLUMN IF EXISTS library_company_id;
    """)
    op.execute("""
    ALTER TABLE financial_statement
      DROP COLUMN IF EXISTS library_company_id;
    """)
    op.execute("""
    ALTER TABLE qualification_certificate
      DROP COLUMN IF EXISTS library_company_id;
    """)
    op.execute("""
    ALTER TABLE project_performance
      DROP COLUMN IF EXISTS library_company_id;
    """)
    op.execute("""
    ALTER TABLE person_profile
      DROP COLUMN IF EXISTS library_company_id;
    """)
    op.execute("""
    ALTER TABLE company_profile
      DROP COLUMN IF EXISTS library_company_id;
    """)
    op.execute("""
    ALTER TABLE bid_template_package
      DROP COLUMN IF EXISTS category_code;
    """)
    op.execute("DROP TABLE IF EXISTS library_company;")
    op.execute("DROP TABLE IF EXISTS template_package_category;")
