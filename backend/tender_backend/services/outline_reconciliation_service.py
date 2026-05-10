"""Outline confirmation gate for template-vs-tender reconciliation."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.db.repositories.bid_outline_repo import BidOutlineRepository
from tender_backend.services.bid_outline_planner import build_bid_outline


class OutlineReconciliationService:
    _CONFLICT_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("separate_volume_submission", re.compile(r"独立成册|单独成册|另册|单独密封|单独提交")),
        ("binding_order", re.compile(r"按顺序装订|装订顺序|目录顺序")),
        ("missing_mandatory_section", re.compile(r"必须提供|应提供|须提供|必须包含|应包含|须包含")),
        ("veto_uncovered", re.compile(r"否决|废标|无效投标|实质性不响应")),
    )

    def build_template_conflict_record(
        self,
        *,
        source_text: str,
        source_locator: str | None,
        affected_chapter_code: str,
        proposed_action: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        trigger = self._rule_trigger(source_text)
        if trigger is None:
            return {
                "policy": "template_default",
                "status": "not_applicable",
                "trigger": None,
                "affected_chapter_code": affected_chapter_code,
                "source_locator": source_locator,
                "proposed_action": proposed_action,
                "reason": "未命中确定性招标文件目录冲突触发器，保持用户提供的目录模板",
            }
        return {
            "policy": "tender_conflict_override",
            "status": "draft",
            "trigger": trigger,
            "affected_chapter_code": affected_chapter_code,
            "source_locator": source_locator,
            "proposed_action": proposed_action,
            "reason": reason or "招标文件存在确定性目录/分册/递交冲突，需人工确认后覆盖模板",
        }

    def _rule_trigger(self, source_text: str) -> str | None:
        text = str(source_text or "")
        for trigger, pattern in self._CONFLICT_TRIGGERS:
            if pattern.search(text):
                return trigger
        return None

    def preview(self, conn: Connection, *, project_id: UUID) -> dict[str, Any]:
        outline = BidOutlineRepository().get_latest_by_project(conn, project_id=project_id)
        if outline is None:
            outline = build_bid_outline(conn, project_id=project_id)
        unresolved = self._unresolved_critical_requirements(conn, project_id=project_id)
        diffs = []
        for chapter in outline.get("chapters", []):
            conflict = self._confirmed_template_conflict(chapter)
            if conflict:
                diffs.append(
                    {
                        "chapter_id": str(chapter["id"]),
                        "chapter_code": chapter["chapter_code"],
                        "chapter_title": chapter["chapter_title"],
                        "volume_type": chapter["volume_type"],
                        "operation": "tender_conflict_override",
                        "requirement_count": len(chapter.get("requirement_ids") or []),
                        "reason": conflict.get("reason") or "招标文件存在已确认目录冲突，按招标文件覆盖模板",
                        "source_locator": conflict.get("source_locator"),
                        "proposed_action": conflict.get("proposed_action"),
                    }
                )
                continue
            op = "keep_mapped" if chapter.get("requirement_ids") else "keep_template"
            diffs.append(
                {
                    "chapter_id": str(chapter["id"]),
                    "chapter_code": chapter["chapter_code"],
                    "chapter_title": chapter["chapter_title"],
                    "volume_type": chapter["volume_type"],
                    "operation": op,
                    "requirement_count": len(chapter.get("requirement_ids") or []),
                    "reason": "按已确认约束映射到目录模板章节" if op == "keep_mapped" else "无招标文件目录冲突，按用户提供的目录模板保留",
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

    def _confirmed_template_conflict(self, chapter: dict[str, Any]) -> dict[str, Any] | None:
        metadata = chapter.get("metadata_json") or {}
        if not isinstance(metadata, dict):
            return None
        conflict = metadata.get("template_conflict")
        if not isinstance(conflict, dict):
            return None
        if conflict.get("policy") != "tender_conflict_override":
            return None
        if conflict.get("status") != "confirmed":
            return None
        return conflict


__all__ = ["OutlineReconciliationService"]
