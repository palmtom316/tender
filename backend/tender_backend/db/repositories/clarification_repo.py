from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ClarificationRepository:
    def create(self, conn: Connection, *, project_id: UUID, fields: dict[str, Any], commit: bool = True) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO tender_clarification (
                  id, project_id, round_no, clarification_type, title, source_file, content_text, impact_json, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    project_id,
                    fields.get("round_no") or 1,
                    fields.get("clarification_type") or "clarification",
                    fields["title"],
                    fields.get("source_file"),
                    fields.get("content_text") or "",
                    Jsonb(fields.get("impact_json") or {}),
                    fields.get("status") or "active",
                ),
            ).fetchone()
        if commit:
            conn.commit()
        return dict(row) if row else {}

    def list_by_project(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM tender_clarification WHERE project_id = %s ORDER BY round_no, created_at",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_impact(
        self,
        conn: Connection,
        *,
        clarification_id: UUID,
        impact_json: dict[str, Any],
        commit: bool = True,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_clarification
                SET impact_json = %s
                WHERE id = %s
                RETURNING *
                """,
                (Jsonb(impact_json), clarification_id),
            ).fetchone()
        if commit:
            conn.commit()
        return dict(row) if row else None


__all__ = ["ClarificationRepository"]
