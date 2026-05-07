"""Outline confirmation gate for template-vs-tender reconciliation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.db.repositories.bid_outline_repo import BidOutlineRepository
from tender_backend.services.bid_outline_planner import build_bid_outline


class OutlineReconciliationService:
    def preview(self, conn: Connection, *, project_id: UUID) -> dict[str, Any]:
        outline = BidOutlineRepository().get_latest_by_project(conn, project_id=project_id)
        if outline is None:
            outline = build_bid_outline(conn, project_id=project_id)
        unresolved = self._unresolved_critical_requirements(conn, project_id=project_id)
        diffs = []
        for chapter in outline.get("chapters", []):
            op = "keep" if chapter.get("requirement_ids") else "mark_manual_required"
            if chapter.get("volume_type") == "pricing":
                op = "mark_external_attached"
            diffs.append(
                {
                    "chapter_id": str(chapter["id"]),
                    "chapter_code": chapter["chapter_code"],
                    "chapter_title": chapter["chapter_title"],
                    "volume_type": chapter["volume_type"],
                    "operation": op,
                    "requirement_count": len(chapter.get("requirement_ids") or []),
                    "reason": "按已解析条款映射" if op == "keep" else "当前章节缺少明确约束，需人工确认保留或补充",
                }
            )
        return {
            "project_id": str(project_id),
            "outline": outline,
            "diffs": diffs,
            "unresolved_critical_count": len(unresolved),
            "can_confirm": len(unresolved) == 0,
            "blocking_requirements": unresolved,
        }

    def confirm(self, conn: Connection, *, project_id: UUID, confirmed_by: str | None = None) -> dict[str, Any]:
        preview = self.preview(conn, project_id=project_id)
        if not preview["can_confirm"]:
            raise ValueError("unresolved critical requirements block outline confirmation")
        outline = preview["outline"]
        metadata = dict(outline.get("metadata_json") or {})
        metadata.update(
            {
                "confirmed_by": confirmed_by,
                "confirmed_diff_count": len(preview["diffs"]),
                "confirmed_outline_gate": True,
            }
        )
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE bid_outline
                SET status = 'confirmed', metadata_json = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (Jsonb(metadata), outline["id"]),
            ).fetchone()
            cur.execute(
                """
                UPDATE project
                SET workflow_status = 'drafting'
                WHERE id = %s
                  AND workflow_status IN ('outline_pending_confirmation', 'constraints_pending_confirmation', 'created', 'source_uploaded')
                """,
                (project_id,),
            )
        conn.commit()
        result = dict(row) if row else outline
        result["diffs"] = preview["diffs"]
        result["confirmed"] = True
        return result

    def latest_confirmed_outline(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            outline = cur.execute(
                """
                SELECT *
                FROM bid_outline
                WHERE project_id = %s AND status = 'confirmed'
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        if outline is None:
            return None
        return BidOutlineRepository().get_latest_by_project(conn, project_id=project_id)

    def _unresolved_critical_requirements(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, category, title, source_file, source_locator
                FROM project_requirement
                WHERE project_id = %s
                  AND COALESCE(review_status, 'pending') <> 'rejected'
                  AND COALESCE(ignored_for_pricing, false) = false
                  AND (
                    COALESCE(is_veto, false) = true
                    OR COALESCE(is_hard_constraint, false) = true
                    OR category IN ('veto', 'qualification', 'performance', 'project_team', 'personnel')
                  )
                  AND COALESCE(human_confirmed, false) = false
                ORDER BY category, created_at
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = ["OutlineReconciliationService"]
