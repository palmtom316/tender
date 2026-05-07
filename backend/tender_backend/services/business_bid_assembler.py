"""Deterministic qualification-business bid assembly service."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


BUSINESS_VOLUMES = {"qualification", "business"}


class BusinessBidAssembler:
    def assemble(self, conn: Connection, *, project_id: UUID, created_by: str | None = None) -> dict[str, Any]:
        outline = self._confirmed_outline(conn, project_id=project_id)
        if outline is None:
            raise ValueError("confirmed outline is required before qualification-business assembly")
        chapters = [row for row in self._outline_chapters(conn, outline_id=outline["id"]) if row["volume_type"] in BUSINESS_VOLUMES]
        missing = self._missing_business_materials(conn, project_id=project_id)
        run = self._create_run(
            conn,
            project_id=project_id,
            outline_id=outline["id"],
            volume_type="business",
            strategy="data_insert",
            status="needs_review" if missing else "completed",
            created_by=created_by,
            metadata={"chapter_count": len(chapters), "missing_material_count": len(missing)},
        )
        return {
            "project_id": str(project_id),
            "run": run,
            "chapters": chapters,
            "response_matrix": self._response_matrix(conn, project_id=project_id, volume_types=BUSINESS_VOLUMES),
            "missing_materials": missing,
            "boundary": "报价内容不由本服务生成；报价分册仅支持外部附件挂载。",
        }

    def _confirmed_outline(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT *
                FROM bid_outline
                WHERE project_id = %s AND status = 'confirmed'
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    def _outline_chapters(self, conn: Connection, *, outline_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, chapter_code, chapter_title, volume_type, sort_order, outline_md, metadata_json
                FROM bid_chapter
                WHERE bid_outline_id = %s
                ORDER BY sort_order, chapter_code
                """,
                (outline_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _missing_business_materials(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT rm.*, pr.title AS requirement_title, pr.category
                FROM requirement_match rm
                JOIN project_requirement pr ON pr.id = rm.requirement_id
                WHERE pr.project_id = %s
                  AND pr.category IN ('qualification', 'performance', 'project_team', 'personnel', 'business')
                  AND rm.match_status IN ('missing', 'needs_review')
                ORDER BY pr.category, pr.created_at
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _response_matrix(self, conn: Connection, *, project_id: UUID, volume_types: set[str]) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT pr.id AS requirement_id, pr.category, pr.title AS requirement_title,
                       bc.chapter_code, bc.chapter_title, bcr.priority_level
                FROM bid_chapter_requirement bcr
                JOIN bid_chapter bc ON bc.id = bcr.bid_chapter_id
                JOIN project_requirement pr ON pr.id = bcr.requirement_id
                WHERE pr.project_id = %s AND bc.volume_type = ANY(%s)
                ORDER BY bc.sort_order, pr.category
                """,
                (project_id, list(volume_types)),
            ).fetchall()
        return [dict(row) for row in rows]

    def _create_run(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        outline_id: UUID,
        volume_type: str,
        strategy: str,
        status: str,
        created_by: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO bid_generation_run (
                  id, project_id, bid_outline_id, volume_type, strategy, status, metadata_json, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), project_id, outline_id, volume_type, strategy, status, Jsonb(metadata), created_by),
            ).fetchone()
        conn.commit()
        return dict(row) if row else {}


__all__ = ["BusinessBidAssembler"]
