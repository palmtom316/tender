"""tag_clauses default fallback provider to siliconflow

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-20
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    UPDATE agent_config
    SET fallback_base_url = 'https://api.siliconflow.cn/v1',
        fallback_model = 'deepseek-ai/DeepSeek-V3.2',
        updated_at = now()
    WHERE agent_key = 'tag_clauses'
      AND base_url = 'https://api.deepseek.com/v1'
      AND primary_model = 'deepseek-chat'
      AND (
        fallback_base_url = ''
        OR fallback_base_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
      )
      AND (
        fallback_model = ''
        OR fallback_model = 'qwen-plus'
      );
    """)


def downgrade() -> None:
    op.execute("""
    UPDATE agent_config
    SET fallback_base_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        fallback_model = 'qwen-plus',
        updated_at = now()
    WHERE agent_key = 'tag_clauses'
      AND base_url = 'https://api.deepseek.com/v1'
      AND primary_model = 'deepseek-chat'
      AND fallback_base_url = 'https://api.siliconflow.cn/v1'
      AND fallback_model = 'deepseek-ai/DeepSeek-V3.2';
    """)
