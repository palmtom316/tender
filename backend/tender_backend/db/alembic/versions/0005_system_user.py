"""system_user and user_session tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-18
"""

from __future__ import annotations

import hashlib
from typing import Sequence, Union

from alembic import op


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _hash_password(password: str) -> str:
    salt = "0" * 32  # fixed seed salt — users should change passwords after first login
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}:{h.hex()}"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS system_user (
      id UUID PRIMARY KEY,
      username VARCHAR(50) NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      display_name VARCHAR(100) NOT NULL,
      role VARCHAR(20) NOT NULL DEFAULT 'editor',
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS user_session (
      token VARCHAR(64) PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES system_user(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days'
    );
    """)

    # Seed default users
    admin_hash = _hash_password("admin123")
    editor_hash = _hash_password("editor123")
    reviewer_hash = _hash_password("reviewer123")

    op.execute(
        f"""
    INSERT INTO system_user (id, username, password_hash, display_name, role)
    VALUES
      (gen_random_uuid(), 'admin',    '{admin_hash}',    '管理员',  'admin'),
      (gen_random_uuid(), 'editor',   '{editor_hash}',   '编辑员',  'editor'),
      (gen_random_uuid(), 'reviewer', '{reviewer_hash}', '复核员',  'reviewer')
    ON CONFLICT (username) DO NOTHING;
    """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_session;")
    op.execute("DROP TABLE IF EXISTS system_user;")
