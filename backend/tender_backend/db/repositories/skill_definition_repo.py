from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class SkillDefinitionRow:
    id: UUID
    skill_name: str
    description: str
    tool_names: list[str]
    prompt_template_id: UUID | None
    version: int
    active: bool
    created_at: datetime


def _row_to_skill(row: dict[str, Any]) -> SkillDefinitionRow:
    return SkillDefinitionRow(
        id=row["id"],
        skill_name=row["skill_name"],
        description=row["description"] or "",
        tool_names=list(row["tool_names"] or []),
        prompt_template_id=row.get("prompt_template_id"),
        version=row["version"],
        active=row["active"],
        created_at=row["created_at"],
    )


_ALL_COLUMNS = (
    "id, skill_name, description, tool_names, prompt_template_id, "
    "version, active, created_at"
)


class SkillDefinitionRepository:
    def list_all(self, conn: Connection) -> list[SkillDefinitionRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_ALL_COLUMNS} FROM skill_definition ORDER BY skill_name"
            ).fetchall()
        return [_row_to_skill(row) for row in rows]

    def get_by_name(self, conn: Connection, skill_name: str) -> SkillDefinitionRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_ALL_COLUMNS} FROM skill_definition WHERE skill_name = %s",
                (skill_name,),
            ).fetchone()
        return _row_to_skill(row) if row else None

    def create(
        self,
        conn: Connection,
        *,
        skill_name: str,
        description: str = "",
        tool_names: list[str] | None = None,
        prompt_template_id: UUID | None = None,
        version: int = 1,
        active: bool = True,
    ) -> SkillDefinitionRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO skill_definition (
                  id, skill_name, description, tool_names, prompt_template_id, version, active
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                RETURNING {_ALL_COLUMNS}
                """,
                (
                    uuid4(),
                    skill_name,
                    description,
                    json.dumps(tool_names or [], ensure_ascii=False),
                    prompt_template_id,
                    version,
                    active,
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _row_to_skill(row)

    def update(self, conn: Connection, skill_name: str, **fields: Any) -> SkillDefinitionRow:
        updatable = {"description", "tool_names", "prompt_template_id", "version", "active"}
        sets: list[str] = []
        values: list[Any] = []
        for col in updatable:
            if col not in fields:
                continue
            value = fields[col]
            if col == "tool_names":
                sets.append(f"{col} = %s::jsonb")
                values.append(json.dumps(value or [], ensure_ascii=False))
            else:
                sets.append(f"{col} = %s")
                values.append(value)

        if not sets:
            row = self.get_by_name(conn, skill_name)
            assert row is not None, f"Skill definition not found: {skill_name}"
            return row

        values.append(skill_name)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE skill_definition
                SET {", ".join(sets)}
                WHERE skill_name = %s
                RETURNING {_ALL_COLUMNS}
                """,
                values,
            ).fetchone()
        conn.commit()
        assert row is not None, f"Skill definition not found: {skill_name}"
        return _row_to_skill(row)

    def delete(self, conn: Connection, *, skill_name: str) -> bool:
        with conn.cursor() as cur:
            row = cur.execute(
                "DELETE FROM skill_definition WHERE skill_name = %s RETURNING id",
                (skill_name,),
            ).fetchone()
        conn.commit()
        return row is not None
