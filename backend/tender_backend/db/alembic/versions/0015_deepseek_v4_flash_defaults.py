"""migrate DeepSeek defaults to v4 flash

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-25
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    UPDATE agent_config
    SET base_url = 'https://api.deepseek.com/v1',
        primary_model = 'deepseek-v4-flash',
        updated_at = now()
    WHERE agent_key IN ('tag_clauses', 'generate_section', 'review_section', 'extract')
      AND primary_model IN ('deepseek-chat', 'deepseek-reasoner', 'deepseek-ai/DeepSeek-V3.2');
    """)


def downgrade() -> None:
    op.execute("""
    UPDATE agent_config
    SET base_url = 'https://api.deepseek.com/v1',
        primary_model = 'deepseek-chat',
        updated_at = now()
    WHERE agent_key IN ('tag_clauses', 'generate_section', 'review_section', 'extract')
      AND base_url = 'https://api.deepseek.com/v1'
      AND primary_model = 'deepseek-v4-flash';
    """)
