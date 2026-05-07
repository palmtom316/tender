"""Technical bid chapter writing gate and run records."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.services.bid_chapter_generation import generate_bid_chapter_draft


class TechnicalBidWriter:
    def create_writing_plan(self, conn: Connection, *, project_id: UUID) -> dict[str, Any]:
        outline = self._confirmed_outline(conn, project_id=project_id)
        if outline is None:
            raise ValueError("confirmed outline is required before technical writing")
        chapters = self._technical_chapters(conn, outline_id=outline["id"])
        return {
            "project_id": str(project_id),
            "outline_id": str(outline["id"]),
            "chapter_count": len(chapters),
            "chapters": [
                {
                    **chapter,
                    "writing_strategy": "plan_generate_check_revise",
                    "required_context": ["confirmed_outline", "mapped_requirements", "business_line", "scoring_criteria"],
                }
                for chapter in chapters
            ],
        }

    def generate_chapter(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        chapter_id: UUID,
        created_by: str | None = None,
        rewrite_note: str | None = None,
    ) -> dict[str, Any]:
        outline = self._confirmed_outline(conn, project_id=project_id)
        if outline is None:
            raise ValueError("confirmed outline is required before technical writing")
        chapter = self._chapter(conn, project_id=project_id, chapter_id=chapter_id)
        if chapter is None or chapter["volume_type"] != "technical":
            raise ValueError("technical chapter not found")
        draft = generate_bid_chapter_draft(conn, project_id=project_id, chapter_id=chapter_id, rewrite_note=rewrite_note)
        run = self._create_run(
            conn,
            project_id=project_id,
            outline_id=outline["id"],
            chapter_id=chapter_id,
            status="completed",
            created_by=created_by,
            metadata={"chapter_code": chapter["chapter_code"], "self_check": self._self_check(draft.get("content_md") or "")},
        )
        return {"project_id": str(project_id), "chapter": chapter, "draft": draft, "run": run}

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

    def _technical_chapters(self, conn: Connection, *, outline_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, chapter_code, chapter_title, volume_type, sort_order, outline_md
                FROM bid_chapter
                WHERE bid_outline_id = %s AND volume_type = 'technical'
                ORDER BY sort_order, chapter_code
                """,
                (outline_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _chapter(self, conn: Connection, *, project_id: UUID, chapter_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM bid_chapter WHERE id = %s AND project_id = %s",
                (chapter_id, project_id),
            ).fetchone()
        return dict(row) if row else None

    def _self_check(self, content: str) -> dict[str, Any]:
        return {
            "has_principle_section": "编制原则" in content,
            "has_response_section": "响应内容" in content,
            "contains_pricing_terms": any(term in content for term in ("投标报价", "单价", "总价")),
        }

    def _create_run(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        outline_id: UUID,
        chapter_id: UUID,
        status: str,
        created_by: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO bid_generation_run (
                  id, project_id, bid_outline_id, bid_chapter_id, volume_type, strategy,
                  status, prompt_inputs_json, metadata_json, created_by
                )
                VALUES (%s, %s, %s, %s, 'technical', 'plan_generate_check_revise', %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    project_id,
                    outline_id,
                    chapter_id,
                    status,
                    Jsonb({"source": "confirmed_outline_and_mapped_requirements"}),
                    Jsonb(metadata),
                    created_by,
                ),
            ).fetchone()
        conn.commit()
        return dict(row) if row else {}


__all__ = ["TechnicalBidWriter"]
