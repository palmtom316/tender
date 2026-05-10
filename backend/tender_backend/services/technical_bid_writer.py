"""Technical bid chapter writing gate and run records."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.services.bid_chapter_generation import generate_bid_chapter_draft
from tender_backend.services.chart_generation_service import ChartGenerationService
from tender_backend.services.technical_chapter_context import TechnicalChapterContextBuilder


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
        context = TechnicalChapterContextBuilder().build(conn, project_id=project_id, chapter_id=chapter_id)
        self._ensure_recommended_charts(conn, project_id=project_id, chapter=chapter, context=context)
        context = TechnicalChapterContextBuilder().build(conn, project_id=project_id, chapter_id=chapter_id)
        draft = generate_bid_chapter_draft(conn, project_id=project_id, chapter_id=chapter_id, context=context, rewrite_note=rewrite_note)
        self_check = self._self_check(draft.get("content_md") or "")
        run = self._create_run(
            conn,
            project_id=project_id,
            outline_id=outline["id"],
            chapter_id=chapter_id,
            status="completed",
            created_by=created_by,
            prompt_inputs=context,
            metadata={
                "chapter_code": chapter["chapter_code"],
                "self_check": self_check,
                "context_hash": _context_hash(context),
                "prompt_version": "technical_chapter_context_v1",
                "generation_mode": "deterministic_strategy_fallback",
            },
        )
        return {"project_id": str(project_id), "chapter": chapter, "draft": draft, "run": run}

    def _ensure_recommended_charts(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        chapter: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        existing = {asset.get("placeholder_key") or asset.get("chart_type") for asset in context.get("chart_assets") or []}
        created: list[dict[str, Any]] = []
        service = ChartGenerationService()
        for chart_type in context.get("recommended_charts") or []:
            if chart_type in existing:
                continue
            spec = service.generate_spec(
                chart_type=chart_type,
                title=_chart_title(chart_type, chapter),
                placeholder_key=chart_type,
                context=context,
            )
            created.append(
                service.create_or_update(
                    conn,
                    project_id=project_id,
                    chart_type=chart_type,
                    title=_chart_title(chart_type, chapter),
                    spec_json=spec,
                    outline_node_id=chapter.get("id"),
                )
            )
        return created

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
        strategy_headings = (
            "质量目标响应",
            "质量管理组织",
            "过程质量控制措施",
            "质量检查与闭环改进",
            "安全文明施工目标",
            "风险识别与分级管控",
            "里程碑计划",
            "关键路径与资源保障",
            "进度预警与纠偏机制",
            "项目组织架构",
            "关键岗位配置",
            "职责分工与协同机制",
            "施工总体部署",
            "关键施工流程",
        )
        strategy_section_count = sum(1 for heading in strategy_headings if f"## {heading}" in content)
        return {
            "has_principle_section": "编制原则" in content,
            "has_response_section": "响应内容" in content or strategy_section_count > 0,
            "has_strategy_sections": strategy_section_count > 0,
            "strategy_section_count": strategy_section_count,
            "chart_placeholder_count": len(re.findall(r"\{\{chart:[^}]+}}", content)),
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
        prompt_inputs: dict[str, Any] | None = None,
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
                    Jsonb(prompt_inputs or {"source": "confirmed_outline_and_mapped_requirements"}),
                    Jsonb(metadata),
                    created_by,
                ),
            ).fetchone()
        conn.commit()
        return dict(row) if row else {}


__all__ = ["TechnicalBidWriter"]


def _context_hash(context: dict[str, Any]) -> str:
    payload = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chart_title(chart_type: str, chapter: dict[str, Any]) -> str:
    names = {
        "org_chart": "项目组织机构图",
        "responsibility_matrix": "岗位职责矩阵",
        "construction_flow": "施工流程图",
        "quality_system": "质量管理体系图",
        "safety_system": "安全管理体系图",
        "risk_matrix": "风险分级管控矩阵",
        "emergency_org": "应急组织架构图",
        "schedule_gantt": "施工进度计划图",
    }
    return names.get(chart_type, f"{chapter.get('chapter_title') or '技术章节'}图表")
