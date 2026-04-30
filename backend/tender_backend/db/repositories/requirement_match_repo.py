"""Repository for requirement_match table."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class RequirementMatchRepository:
    def replace_for_project(self, conn: Connection, *, project_id: UUID, matches: list[dict[str, Any]]) -> list[dict]:
        rows: list[dict] = []
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                DELETE FROM requirement_match
                WHERE requirement_id IN (
                  SELECT id FROM project_requirement WHERE project_id = %s
                )
                """,
                (project_id,),
            )
            for match in matches:
                row = cur.execute(
                    """
                    INSERT INTO requirement_match (
                      id, requirement_id, match_status, matched_source_type,
                      matched_source_id, matched_title, match_score, evidence_summary,
                      missing_reason, requires_human_confirm, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        match["requirement_id"],
                        match["match_status"],
                        match.get("matched_source_type"),
                        match.get("matched_source_id"),
                        match.get("matched_title"),
                        match.get("match_score"),
                        match.get("evidence_summary"),
                        match.get("missing_reason"),
                        match.get("requires_human_confirm", False),
                        Jsonb(match.get("metadata_json") or {}),
                    ),
                ).fetchone()
                if row is not None:
                    rows.append(dict(row))
        conn.commit()
        return rows

    def list_by_project(self, conn: Connection, *, project_id: UUID) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT rm.*, pr.project_id, pr.category, pr.title AS requirement_title
                FROM requirement_match rm
                JOIN project_requirement pr ON pr.id = rm.requirement_id
                WHERE pr.project_id = %s
                ORDER BY pr.category, pr.created_at, rm.match_score DESC NULLS LAST
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]
