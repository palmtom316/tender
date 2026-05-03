"""Repository for scoring_criteria table."""

from __future__ import annotations

from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ScoringRepository:
    def create(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        dimension: str,
        max_score: float,
        scoring_method: str | None = None,
        source_document_id: UUID | None = None,
        source_page: int | None = None,
        source_chunk_id: UUID | None = None,
        source_file: str | None = None,
        source_locator: str | None = None,
        sub_items_json: list | None = None,
        extraction_method: str = "rule",
    ) -> dict:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO scoring_criteria
                    (id, project_id, dimension, max_score, scoring_method,
                     source_document_id, source_page, source_chunk_id, source_file,
                     source_locator, sub_items_json, extraction_method)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), project_id, dimension, max_score, scoring_method,
                 source_document_id, source_page, source_chunk_id, source_file,
                 source_locator, Jsonb(sub_items_json or []), extraction_method),
            ).fetchone()
        conn.commit()
        return row  # type: ignore[return-value]

    def create_many(self, conn: Connection, *, project_id: UUID, criteria: list[dict]) -> list[dict]:
        rows: list[dict] = []
        with conn.cursor(row_factory=dict_row) as cur:
            for item in criteria:
                row = cur.execute(
                    """
                    INSERT INTO scoring_criteria
                        (id, project_id, dimension, max_score, scoring_method,
                         source_document_id, source_page, source_chunk_id, source_file,
                         source_locator, sub_items_json, extraction_method)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        project_id,
                        item["dimension"],
                        item.get("max_score", 0),
                        item.get("scoring_method"),
                        item.get("source_document_id"),
                        item.get("source_page"),
                        item.get("source_chunk_id"),
                        item.get("source_file"),
                        item.get("source_locator"),
                        Jsonb(item.get("sub_items_json") or []),
                        item.get("extraction_method", "rule"),
                    ),
                ).fetchone()
                if row is not None:
                    rows.append(dict(row))
        conn.commit()
        return rows

    def list_by_project(self, conn: Connection, *, project_id: UUID) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM scoring_criteria WHERE project_id = %s ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return rows

    def confirm(
        self,
        conn: Connection,
        *,
        criteria_id: UUID,
        confirmed_by: str,
    ) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE scoring_criteria
                SET human_confirmed = TRUE, confirmed_by = %s, confirmed_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (confirmed_by, criteria_id),
            ).fetchone()
        conn.commit()
        return row
