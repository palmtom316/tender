from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class AgentConfigRow:
    id: UUID
    agent_key: str
    display_name: str
    description: str
    agent_type: str
    base_url: str
    api_key: str
    primary_model: str
    fallback_base_url: str
    fallback_api_key: str
    fallback_model: str
    enabled: bool
    updated_at: datetime


def _row_to_config(row: dict[str, Any]) -> AgentConfigRow:
    return AgentConfigRow(
        id=row["id"],
        agent_key=row["agent_key"],
        display_name=row["display_name"],
        description=row["description"],
        agent_type=row["agent_type"],
        base_url=row["base_url"],
        api_key=row["api_key"],
        primary_model=row["primary_model"],
        fallback_base_url=row["fallback_base_url"],
        fallback_api_key=row["fallback_api_key"],
        fallback_model=row["fallback_model"],
        enabled=row["enabled"],
        updated_at=row["updated_at"],
    )


_ALL_COLUMNS = (
    "id, agent_key, display_name, description, agent_type, "
    "base_url, api_key, primary_model, "
    "fallback_base_url, fallback_api_key, fallback_model, "
    "enabled, updated_at"
)


class AgentConfigRepository:
    def list_all(self, conn: Connection) -> list[AgentConfigRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_ALL_COLUMNS} FROM agent_config ORDER BY agent_key"
            ).fetchall()
        return [_row_to_config(r) for r in rows]

    def get_by_key(self, conn: Connection, agent_key: str) -> AgentConfigRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_ALL_COLUMNS} FROM agent_config WHERE agent_key = %s",
                (agent_key,),
            ).fetchone()
        return _row_to_config(row) if row else None

    def upsert(self, conn: Connection, agent_key: str, **fields: Any) -> AgentConfigRow:
        # Build SET clause from non-None fields
        updatable = {
            "base_url", "api_key", "primary_model",
            "fallback_base_url", "fallback_api_key", "fallback_model",
            "enabled", "display_name", "description",
        }
        sets: list[str] = []
        values: list[Any] = []
        for col in updatable:
            if col in fields and fields[col] is not None:
                sets.append(f"{col} = %s")
                values.append(fields[col])

        if not sets:
            # Nothing to update — return current row
            row = self.get_by_key(conn, agent_key)
            assert row is not None, f"Agent config not found: {agent_key}"
            return row

        sets.append("updated_at = now()")
        values.append(agent_key)

        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"UPDATE agent_config SET {', '.join(sets)} "
                f"WHERE agent_key = %s "
                f"RETURNING {_ALL_COLUMNS}",
                values,
            ).fetchone()
        conn.commit()
        assert row is not None, f"Agent config not found: {agent_key}"
        return _row_to_config(row)
