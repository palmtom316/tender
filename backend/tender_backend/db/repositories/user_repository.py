from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


# ── Password utilities ──


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}:{h.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    parts = stored_hash.split(":", 1)
    if len(parts) != 2:
        return False
    salt, expected = parts
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return h.hex() == expected


# ── Data classes ──


@dataclass(frozen=True)
class SystemUser:
    id: UUID
    username: str
    display_name: str
    role: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


_USER_COLUMNS = "id, username, display_name, role, enabled, created_at, updated_at"


def _row_to_user(row: dict[str, Any]) -> SystemUser:
    return SystemUser(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        role=row["role"],
        enabled=row["enabled"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class UserRepository:
    def list_all(self, conn: Connection) -> list[SystemUser]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_USER_COLUMNS} FROM system_user ORDER BY created_at"
            ).fetchall()
        return [_row_to_user(r) for r in rows]

    def get_by_id(self, conn: Connection, user_id: UUID) -> SystemUser | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_USER_COLUMNS} FROM system_user WHERE id = %s",
                (user_id,),
            ).fetchone()
        return _row_to_user(row) if row else None

    def get_by_username(self, conn: Connection, username: str) -> tuple[SystemUser, str] | None:
        """Return (user, password_hash) for login validation."""
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_USER_COLUMNS}, password_hash FROM system_user WHERE username = %s",
                (username,),
            ).fetchone()
        if not row:
            return None
        return _row_to_user(row), row["password_hash"]

    def create(self, conn: Connection, *, username: str, password: str, display_name: str, role: str) -> SystemUser:
        user_id = uuid4()
        pw_hash = hash_password(password)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"INSERT INTO system_user (id, username, password_hash, display_name, role) "
                f"VALUES (%s, %s, %s, %s, %s) RETURNING {_USER_COLUMNS}",
                (user_id, username, pw_hash, display_name, role),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _row_to_user(row)

    def update(self, conn: Connection, user_id: UUID, **fields: Any) -> SystemUser | None:
        updatable = {"display_name", "role", "enabled"}
        sets: list[str] = []
        values: list[Any] = []

        for col in updatable:
            if col in fields and fields[col] is not None:
                sets.append(f"{col} = %s")
                values.append(fields[col])

        # Handle password change separately
        if "password" in fields and fields["password"]:
            sets.append("password_hash = %s")
            values.append(hash_password(fields["password"]))

        if not sets:
            return self.get_by_id(conn, user_id)

        sets.append("updated_at = now()")
        values.append(user_id)

        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"UPDATE system_user SET {', '.join(sets)} WHERE id = %s RETURNING {_USER_COLUMNS}",
                values,
            ).fetchone()
        conn.commit()
        return _row_to_user(row) if row else None

    def delete(self, conn: Connection, user_id: UUID) -> bool:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM system_user WHERE id = %s", (user_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted


# ── Session management ──


class SessionRepository:
    def create_session(self, conn: Connection, user_id: UUID) -> str:
        token = secrets.token_hex(32)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_session (token, user_id) VALUES (%s, %s)",
                (token, user_id),
            )
        conn.commit()
        return token

    def get_user_by_token(self, conn: Connection, token: str) -> SystemUser | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT u.id, u.username, u.display_name, u.role, u.enabled, "
                "u.created_at, u.updated_at "
                "FROM user_session s JOIN system_user u ON s.user_id = u.id "
                "WHERE s.token = %s AND s.expires_at > now() AND u.enabled = TRUE",
                (token,),
            ).fetchone()
        return _row_to_user(row) if row else None

    def delete_session(self, conn: Connection, token: str) -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_session WHERE token = %s", (token,))
        conn.commit()
