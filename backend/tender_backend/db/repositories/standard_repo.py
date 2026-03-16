"""Repository for standard and standard_clause tables."""

from __future__ import annotations

from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


class StandardRepository:
    def create_standard(
        self,
        conn: Connection,
        *,
        standard_code: str,
        standard_name: str,
        version_year: str | None = None,
        specialty: str | None = None,
        document_id: UUID | None = None,
    ) -> dict:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO standard
                    (id, standard_code, standard_name, version_year, specialty, document_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), standard_code, standard_name, version_year, specialty, document_id),
            ).fetchone()
        conn.commit()
        return row  # type: ignore[return-value]

    def create_clause(
        self,
        conn: Connection,
        *,
        standard_id: UUID,
        clause_no: str | None = None,
        clause_title: str | None = None,
        clause_text: str,
        summary: str | None = None,
        tags: list[str] | None = None,
        parent_id: UUID | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
        sort_order: int = 0,
    ) -> dict:
        import json
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO standard_clause
                    (id, standard_id, parent_id, clause_no, clause_title,
                     clause_text, summary, tags, page_start, page_end, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(), standard_id, parent_id, clause_no, clause_title,
                    clause_text, summary, json.dumps(tags or []),
                    page_start, page_end, sort_order,
                ),
            ).fetchone()
        conn.commit()
        return row  # type: ignore[return-value]

    def list_standards(self, conn: Connection) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT * FROM standard ORDER BY standard_code"
            ).fetchall()

    def list_clauses(
        self, conn: Connection, *, standard_id: UUID
    ) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT * FROM standard_clause WHERE standard_id = %s ORDER BY sort_order",
                (standard_id,),
            ).fetchall()
