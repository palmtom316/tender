"""add updated_at to tender constraint set

Revision ID: 0054
Revises: 0053
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tender_constraint_set "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();"
    )
    op.execute("UPDATE tender_constraint_set SET updated_at = created_at WHERE updated_at IS NULL;")


def downgrade() -> None:
    op.execute("ALTER TABLE tender_constraint_set DROP COLUMN IF EXISTS updated_at;")
