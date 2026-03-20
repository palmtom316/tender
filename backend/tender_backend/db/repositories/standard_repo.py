"""Repository for standard and standard_clause tables."""

from __future__ import annotations

import json as _json
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


class StandardRepository:
    # ── Read helpers ──

    def get_standard(self, conn: Connection, standard_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT s.*, j.ocr_status, j.ai_status
                FROM standard s
                LEFT JOIN standard_processing_job j ON j.standard_id = s.id
                WHERE s.id = %s
                """,
                (standard_id,),
            ).fetchone()

    def get_standard_file(self, conn: Connection, standard_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT
                  s.id AS standard_id,
                  d.id AS document_id,
                  pf.id AS project_file_id,
                  pf.filename,
                  pf.content_type,
                  pf.storage_key
                FROM standard s
                JOIN document d ON d.id = s.document_id
                JOIN project_file pf ON pf.id = d.project_file_id
                WHERE s.id = %s
                """,
                (standard_id,),
            ).fetchone()

    def get_clause(self, conn: Connection, clause_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT
                  sc.*,
                  s.standard_name,
                  s.specialty
                FROM standard_clause sc
                JOIN standard s ON s.id = sc.standard_id
                WHERE sc.id = %s
                """,
                (clause_id,),
            ).fetchone()

    def get_clauses_by_ids(self, conn: Connection, clause_ids: list[UUID]) -> dict[str, dict]:
        if not clause_ids:
            return {}

        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT
                  sc.*,
                  s.standard_name,
                  s.specialty
                FROM standard_clause sc
                JOIN standard s ON s.id = sc.standard_id
                WHERE sc.id = ANY(%s)
                """,
                (clause_ids,),
            ).fetchall()

        return {str(row["id"]): row for row in rows}

    def list_neighbor_clauses(
        self,
        conn: Connection,
        *,
        standard_id: UUID,
        sort_order: int,
        radius: int = 2,
    ) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT *
                FROM standard_clause
                WHERE standard_id = %s
                  AND sort_order BETWEEN %s AND %s
                ORDER BY sort_order
                """,
                (standard_id, sort_order - radius, sort_order + radius),
            ).fetchall()

    def get_clause_count(self, conn: Connection, standard_id: UUID) -> int:
        with conn.cursor() as cur:
            row = cur.execute(
                "SELECT count(*) FROM standard_clause WHERE standard_id = %s",
                (standard_id,),
            ).fetchone()
            return row[0] if row else 0

    def get_clause_tree(self, conn: Connection, standard_id: UUID) -> list[dict]:
        """Fetch clauses and rebuild nested children tree in Python."""
        flat = self.list_clauses(conn, standard_id=standard_id)
        if not flat:
            return []

        # Index by id
        by_id: dict[str, dict] = {}
        for c in flat:
            node = {
                "id": str(c["id"]),
                "clause_no": c.get("clause_no"),
                "clause_title": c.get("clause_title"),
                "clause_text": c.get("clause_text"),
                "summary": c.get("summary"),
                "tags": c.get("tags", []),
                "clause_type": c.get("clause_type", "normative"),
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "sort_order": c.get("sort_order"),
                "parent_id": str(c["parent_id"]) if c.get("parent_id") else None,
                "children": [],
            }
            by_id[str(c["id"])] = node

        roots: list[dict] = []
        for node in by_id.values():
            pid = node["parent_id"]
            if pid and pid in by_id:
                by_id[pid]["children"].append(node)
            else:
                roots.append(node)

        return roots

    # ── Write helpers ──

    def update_processing_status(
        self,
        conn: Connection,
        standard_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> None:
        ts_col = (
            "processing_started_at" if status == "processing"
            else "processing_finished_at" if status in ("completed", "failed")
            else None
        )
        if ts_col:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE standard SET processing_status = %s, error_message = %s, {ts_col} = now() WHERE id = %s",
                    (status, error_message, standard_id),
                )
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE standard SET processing_status = %s, error_message = %s WHERE id = %s",
                    (status, error_message, standard_id),
                )
        conn.commit()

    def bulk_create_clauses(self, conn: Connection, clauses: list[dict]) -> int:
        """Bulk insert clause dicts. Returns count inserted."""
        if not clauses:
            return 0
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO standard_clause
                       (id, standard_id, parent_id, clause_no, clause_title,
                        clause_text, summary, tags, page_start, page_end,
                        sort_order, clause_type, commentary_clause_id)
                   VALUES (%(id)s, %(standard_id)s, %(parent_id)s, %(clause_no)s,
                           %(clause_title)s, %(clause_text)s, %(summary)s,
                           %(tags)s, %(page_start)s, %(page_end)s,
                           %(sort_order)s, %(clause_type)s, %(commentary_clause_id)s)""",
                [
                    {
                        **c,
                        "tags": _json.dumps(c.get("tags") or []),
                        "commentary_clause_id": c.get("commentary_clause_id"),
                    }
                    for c in clauses
                ],
            )
        conn.commit()
        return len(clauses)

    def delete_clauses(self, conn: Connection, standard_id: UUID) -> int:
        """Delete all clauses for a standard (supports re-processing)."""
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM standard_clause WHERE standard_id = %s", (standard_id,)
            )
            count = cur.rowcount
        conn.commit()
        return count

    def delete_standard(self, conn: Connection, *, standard_id: UUID) -> int:
        file_meta = self.get_standard_file(conn, standard_id)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM standard WHERE id = %s", (standard_id,))
            deleted = cur.rowcount
            if deleted and file_meta and file_meta.get("project_file_id"):
                cur.execute(
                    "DELETE FROM project_file WHERE id = %s",
                    (file_meta["project_file_id"],),
                )
        conn.commit()
        return deleted

    # ── Original methods ──
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
                """
                SELECT s.*, j.ocr_status, j.ai_status
                FROM standard s
                LEFT JOIN standard_processing_job j ON j.standard_id = s.id
                ORDER BY s.standard_code
                """
            ).fetchall()

    def list_clauses(
        self, conn: Connection, *, standard_id: UUID
    ) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT * FROM standard_clause WHERE standard_id = %s ORDER BY sort_order",
                (standard_id,),
            ).fetchall()
