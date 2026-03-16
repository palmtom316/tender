"""phase 2 supplementary tables — 5 new tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- task_trace: AI 调用追踪 ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS task_trace (
      id UUID PRIMARY KEY,
      workflow_run_id UUID REFERENCES workflow_run(id) ON DELETE SET NULL,
      task_type VARCHAR(100) NOT NULL,
      model VARCHAR(100),
      provider VARCHAR(100),
      prompt_version VARCHAR(50),
      input_tokens INT,
      output_tokens INT,
      estimated_cost NUMERIC(10,6),
      latency_ms INT,
      status VARCHAR(32) NOT NULL DEFAULT 'pending',
      error TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- prompt_template: Prompt 版本管理 ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS prompt_template (
      id UUID PRIMARY KEY,
      prompt_name VARCHAR(100) NOT NULL,
      version INT NOT NULL DEFAULT 1,
      template_text TEXT NOT NULL,
      variables JSONB NOT NULL DEFAULT '[]'::jsonb,
      description TEXT,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (prompt_name, version)
    );
    """)

    # --- model_profile: 模型配置 ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS model_profile (
      id UUID PRIMARY KEY,
      profile_name VARCHAR(100) NOT NULL UNIQUE,
      provider VARCHAR(100) NOT NULL,
      model_name VARCHAR(100) NOT NULL,
      is_primary BOOLEAN NOT NULL DEFAULT FALSE,
      temperature NUMERIC(3,2) DEFAULT 0.3,
      max_tokens INT DEFAULT 4096,
      timeout_seconds INT DEFAULT 60,
      retry_count INT DEFAULT 2,
      config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- tool_definition: 工具定义 ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS tool_definition (
      id UUID PRIMARY KEY,
      tool_name VARCHAR(100) NOT NULL UNIQUE,
      description TEXT,
      input_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
      output_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
      version INT NOT NULL DEFAULT 1,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # --- skill_definition: 技能定义 ---
    op.execute("""
    CREATE TABLE IF NOT EXISTS skill_definition (
      id UUID PRIMARY KEY,
      skill_name VARCHAR(100) NOT NULL UNIQUE,
      description TEXT,
      tool_names JSONB NOT NULL DEFAULT '[]'::jsonb,
      prompt_template_id UUID REFERENCES prompt_template(id) ON DELETE SET NULL,
      version INT NOT NULL DEFAULT 1,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS skill_definition;")
    op.execute("DROP TABLE IF EXISTS tool_definition;")
    op.execute("DROP TABLE IF EXISTS model_profile;")
    op.execute("DROP TABLE IF EXISTS prompt_template;")
    op.execute("DROP TABLE IF EXISTS task_trace;")
