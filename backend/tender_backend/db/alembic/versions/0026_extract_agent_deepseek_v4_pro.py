"""set tender extraction default model

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    UPDATE agent_config
    SET description = '招标文件 AI 解析、需求分类、事实提取、评分结构化',
        base_url = 'https://api.deepseek.com',
        primary_model = 'deepseek-v4-pro',
        updated_at = now()
    WHERE agent_key = 'extract'
      AND primary_model IN ('', 'deepseek-chat', 'deepseek-reasoner', 'deepseek-v4-flash', 'deepseek-v4-pro-max', 'deepseek-ai/DeepSeek-V3.2');
    """)


def downgrade() -> None:
    op.execute("""
    UPDATE agent_config
    SET primary_model = 'deepseek-v4-flash',
        updated_at = now()
    WHERE agent_key = 'extract'
      AND primary_model = 'deepseek-v4-pro';
    """)
