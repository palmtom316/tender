"""Repository for project_requirement table."""

from __future__ import annotations

from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


class RequirementRepository:
    def create(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        category: str,
        title: str,
        source_text: str | None = None,
    ) -> dict:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO project_requirement
                    (id, project_id, category, title, source_text)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), project_id, category, title, source_text),
            ).fetchone()
        conn.commit()
        return row  # type: ignore[return-value]

    def list_by_project(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        category: str | None = None,
    ) -> list[dict]:
        query = "SELECT * FROM project_requirement WHERE project_id = %s"
        params: list = [project_id]
        if category:
            query += " AND category = %s"
            params.append(category)
        query += " ORDER BY created_at"
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(query, params).fetchall()
        return rows

    def confirm(
        self,
        conn: Connection,
        *,
        requirement_id: UUID,
        confirmed_by: str,
    ) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE project_requirement
                SET human_confirmed = TRUE, confirmed_by = %s, confirmed_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (confirmed_by, requirement_id),
            ).fetchone()
        conn.commit()
        return row

    def unconfirmed_veto_count(self, conn: Connection, *, project_id: UUID) -> int:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT COUNT(*) AS c FROM project_requirement
                WHERE project_id = %s AND category = 'veto' AND human_confirmed = FALSE
                """,
                (project_id,),
            ).fetchone()
        return row["c"] if row else 0  # type: ignore[index]
