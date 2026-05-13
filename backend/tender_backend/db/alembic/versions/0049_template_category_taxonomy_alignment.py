"""align template categories with tender template kinds

Revision ID: 0049
Revises: 0048
Create Date: 2026-05-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    INSERT INTO template_package_category (code, display_name, description, sort_order, enabled)
    VALUES
      ('sgcc_substation', '国网变电工程', '国家电网变电工程类项目模板', 10, TRUE),
      ('sgcc_maintenance', '国网运维工程', '国家电网运维类项目模板', 20, TRUE),
      ('sgcc_distribution', '国网配网工程', '国家电网配网工程类项目模板', 30, TRUE),
      ('sgcc_low_voltage_distribution', '国网低压营配工程', '国家电网低压营配工程类项目模板', 40, TRUE),
      ('user_distribution', '用户配电工程', '用户侧配电工程类项目模板', 50, TRUE),
      ('user_maintenance', '用户运维工程', '用户侧运维工程类项目模板', 60, TRUE)
    ON CONFLICT (code) DO UPDATE SET
      display_name = EXCLUDED.display_name,
      description = EXCLUDED.description,
      sort_order = EXCLUDED.sort_order,
      enabled = EXCLUDED.enabled,
      updated_at = now();
    """)
    op.execute("""
    UPDATE bid_template_package
    SET category_code = CASE category_code
      WHEN 'sgcc_operation' THEN 'sgcc_maintenance'
      WHEN 'sgcc_10kv' THEN 'sgcc_distribution'
      WHEN 'user_operation' THEN 'user_maintenance'
      ELSE category_code
    END
    WHERE category_code IN ('sgcc_operation', 'sgcc_10kv', 'user_operation');
    """)
    op.execute("""
    DELETE FROM template_package_category
    WHERE code IN ('sgcc_operation', 'sgcc_10kv', 'user_operation');
    """)


def downgrade() -> None:
    op.execute("""
    INSERT INTO template_package_category (code, display_name, description, sort_order, enabled)
    VALUES
      ('sgcc_operation', '国网运维工程', '国家电网运维类项目模板', 10, TRUE),
      ('sgcc_10kv', '国网10KV工程', '国家电网10KV工程类项目模板', 30, TRUE),
      ('user_operation', '用户运维工程', '用户侧运维工程类项目模板', 50, TRUE)
    ON CONFLICT (code) DO UPDATE SET
      display_name = EXCLUDED.display_name,
      description = EXCLUDED.description,
      sort_order = EXCLUDED.sort_order,
      enabled = EXCLUDED.enabled,
      updated_at = now();
    """)
    op.execute("""
    UPDATE bid_template_package
    SET category_code = CASE category_code
      WHEN 'sgcc_maintenance' THEN 'sgcc_operation'
      WHEN 'sgcc_distribution' THEN 'sgcc_10kv'
      WHEN 'user_maintenance' THEN 'user_operation'
      ELSE category_code
    END
    WHERE category_code IN ('sgcc_maintenance', 'sgcc_distribution', 'user_maintenance');
    """)
    op.execute("""
    DELETE FROM template_package_category
    WHERE code IN ('sgcc_maintenance', 'sgcc_distribution', 'user_maintenance');
    """)
