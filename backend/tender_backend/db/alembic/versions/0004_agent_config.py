"""agent_config table — per-agent AI model configuration

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS agent_config (
      id UUID PRIMARY KEY,
      agent_key VARCHAR(50) NOT NULL UNIQUE,
      display_name VARCHAR(100) NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      agent_type VARCHAR(20) NOT NULL DEFAULT 'llm',
      base_url TEXT NOT NULL DEFAULT '',
      api_key TEXT NOT NULL DEFAULT '',
      primary_model VARCHAR(100) NOT NULL DEFAULT '',
      fallback_base_url TEXT NOT NULL DEFAULT '',
      fallback_api_key TEXT NOT NULL DEFAULT '',
      fallback_model VARCHAR(100) NOT NULL DEFAULT '',
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # Seed default rows
    op.execute("""
    INSERT INTO agent_config (id, agent_key, display_name, description, agent_type, base_url, primary_model, fallback_base_url, fallback_model)
    VALUES
      (gen_random_uuid(), 'parse',            '文档解析 (OCR)',  '招标文件 OCR、表格/标题提取',       'ocr', '',                                    '',                '', ''),
      (gen_random_uuid(), 'extract',          '智能提取',        '需求分类、事实提取、评分结构化',     'llm', 'https://api.deepseek.com/v1',         'deepseek-chat',   'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-plus'),
      (gen_random_uuid(), 'generate_section', '章节生成',        '章节大纲 + 正文生成',               'llm', 'https://api.deepseek.com/v1',         'deepseek-chat',   'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-plus'),
      (gen_random_uuid(), 'review_section',   '质量审查',        '合规审查、一致性校验',              'llm', 'https://api.deepseek.com/v1',         'deepseek-chat',   'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-plus'),
      (gen_random_uuid(), 'tag_clauses',      '规范标注',        '条文树构建、标签、摘要',            'llm', 'https://api.siliconflow.cn/v1',       'deepseek-ai/DeepSeek-V3.2', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-plus')
    ON CONFLICT (agent_key) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_config;")
