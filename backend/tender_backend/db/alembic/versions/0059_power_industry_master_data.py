"""power industry master data

Revision ID: 0059
Revises: 0058
Create Date: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    COMMENT ON COLUMN qualification_certificate.certificate_type IS
      'Free text. Recommended power-industry values include 承装（修、试）电力设施许可证, 输变电工程专业承包, 电力工程施工总承包.';
    """)
    op.execute("""
    COMMENT ON COLUMN qualification_certificate.grade IS
      'Free text. Recommended power-industry grades include 一级, 二级, 三级, 四级, 五级.';
    """)
    op.execute("""
    COMMENT ON COLUMN project_performance.metadata_json IS
      'Free-form metadata. Power-industry fields may include voltage_level_kv, circuit_count, capacity_mva, distribution_type, is_live_work.';
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_qualification_certificate_power_type
      ON qualification_certificate(certificate_type, grade)
      WHERE certificate_type IN ('承装（修、试）电力设施许可证', '输变电工程专业承包', '电力工程施工总承包');
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_project_performance_power_metadata
      ON project_performance USING GIN (metadata_json)
      WHERE metadata_json ?| ARRAY['voltage_level_kv', 'circuit_count', 'capacity_mva', 'distribution_type', 'is_live_work'];
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_project_performance_voltage_level
      ON project_performance((metadata_json->>'voltage_level_kv'))
      WHERE metadata_json ? 'voltage_level_kv';
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_performance_voltage_level;")
    op.execute("DROP INDEX IF EXISTS idx_project_performance_power_metadata;")
    op.execute("DROP INDEX IF EXISTS idx_qualification_certificate_power_type;")
    op.execute("COMMENT ON COLUMN project_performance.metadata_json IS NULL;")
    op.execute("COMMENT ON COLUMN qualification_certificate.grade IS NULL;")
    op.execute("COMMENT ON COLUMN qualification_certificate.certificate_type IS NULL;")
