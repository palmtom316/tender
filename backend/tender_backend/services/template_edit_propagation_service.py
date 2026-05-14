from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class TemplateEditPropagationService:
    DOCX_STALE_BLOCKS = {
        "fixed_text",
        "table_definition",
        "asset_placeholder",
        "ai_prompt",
        "chart_prompt",
        "page_format",
        "page_break",
        "header_footer",
    }

    def classify_block_edit(self, block_type: str, before: dict[str, Any] | None = None, after: dict[str, Any] | None = None) -> dict[str, bool]:
        return {
            "stales_docx": block_type in self.DOCX_STALE_BLOCKS,
            "stales_draft": block_type == "ai_prompt",
            "stales_chart": block_type == "chart_prompt",
        }

    def apply_stale_impact(self, conn: Connection, *, block: Any, revision_no: int, actor: str | None = None) -> dict[str, int]:
        block_type = getattr(block, "block_type", "")
        classification = self.classify_block_edit(block_type)
        impact = {
            "stale_drafts": 0,
            "stale_charts": 0,
            "stale_docx": 1 if classification["stales_docx"] else 0,
            "stale_draft_count": 0,
            "stale_chart_count": 0,
            "stale_export_artifact_count": 1 if classification["stales_docx"] else 0,
        }
        if not hasattr(conn, "cursor"):
            if classification["stales_draft"]:
                impact["stale_drafts"] = 1
                impact["stale_draft_count"] = 1
            if classification["stales_chart"]:
                impact["stale_charts"] = 1
                impact["stale_chart_count"] = 1
            return impact

        with conn.cursor(row_factory=dict_row) as cur:
            if classification["stales_docx"]:
                row = cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM export_record
                    WHERE project_id = %s
                      AND status = 'completed'
                    """,
                    (block.project_id,),
                ).fetchone()
                export_count = int((row or {}).get("count") or 0)
                impact["stale_docx"] = export_count
                impact["stale_export_artifact_count"] = export_count
            chapter = cur.execute(
                """
                SELECT id, volume_type, chapter_code
                FROM project_template_chapter
                WHERE id = %s
                """,
                (block.template_chapter_id,),
            ).fetchone()
            if classification["stales_draft"] and chapter is not None:
                stale_reason = f"项目模板修订 {revision_no} 更新了本章 AI 提示词，需按新模板重新生成正文。"
                cur.execute(
                    """
                    UPDATE chapter_draft
                    SET is_stale_by_template = true,
                        template_stale_reason = %s,
                        stale_by_template_revision_no = %s,
                        stale_by_template_block_id = %s,
                        updated_at = now()
                    WHERE project_id = %s
                      AND volume_type = %s
                      AND chapter_code = %s
                    """,
                    (stale_reason, revision_no, block.id, block.project_id, chapter["volume_type"], chapter["chapter_code"]),
                )
                impact["stale_drafts"] = max(cur.rowcount or 0, 0)
                impact["stale_draft_count"] = impact["stale_drafts"]
            if classification["stales_chart"]:
                stale_reason = f"项目模板修订 {revision_no} 更新了图表生成提示词，需按新模板重新生成图表。"
                metadata = {"template_stale_reason": stale_reason, "stale_by_template_revision_no": revision_no, "stale_by_template_actor": actor}
                where = """
                    project_id = %s
                    AND (
                      spec_json->>'chapter_code' = %s
                      OR metadata_json->>'chapter_code' = %s
                      OR metadata_json #>> '{source_context,chapter_code}' = %s
                    )
                """
                params: tuple[Any, ...] = (
                    Jsonb(metadata),
                    revision_no,
                    block.id,
                    stale_reason,
                    block.project_id,
                    chapter["chapter_code"] if chapter else "",
                    chapter["chapter_code"] if chapter else "",
                    chapter["chapter_code"] if chapter else "",
                )
                placeholder_key = getattr(block, "placeholder_key", None)
                if placeholder_key:
                    where += " AND (placeholder_key = %s OR chart_type = %s)"
                    params = (*params, placeholder_key, placeholder_key)
                cur.execute(
                    f"""
                    UPDATE chart_asset
                    SET status = 'stale_pending_regeneration',
                        is_stale_by_template = true,
                        stale_by_template_revision_no = %s,
                        stale_by_template_block_id = %s,
                        template_stale_reason = %s,
                        metadata_json = COALESCE(metadata_json, '{{}}'::jsonb) || %s,
                        updated_at = now()
                    WHERE {where}
                    """,
                    (params[1], params[2], params[3], params[0], *params[4:]),
                )
                impact["stale_charts"] = max(cur.rowcount or 0, 0)
                impact["stale_chart_count"] = impact["stale_charts"]
            impact["stale_export_artifact_count"] = max(impact["stale_drafts"], impact["stale_charts"], impact["stale_docx"])
        return impact
