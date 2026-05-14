"""Technical bid chapter writing gate and run records."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.core.config import get_settings
from tender_backend.services.ai_gateway_client import ai_gateway_headers
from tender_backend.services.bid_chapter_generation import CHART_PLACEHOLDER_RE, generate_bid_chapter_draft
from tender_backend.services.chart_generation_service import ChartGenerationService
from tender_backend.services.project_template_instance_service import ProjectTemplateInstanceService
from tender_backend.services.technical_chapter_context import TechnicalChapterContextBuilder, with_target_pages_override


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
        target_pages: int | None = None,
    ) -> dict[str, Any]:
        outline = self._confirmed_outline(conn, project_id=project_id)
        if outline is None:
            raise ValueError("confirmed outline is required before technical writing")
        chapter = self._chapter(conn, project_id=project_id, chapter_id=chapter_id)
        if chapter is None or chapter["volume_type"] != "technical":
            raise ValueError("technical chapter not found")
        context = with_target_pages_override(
            TechnicalChapterContextBuilder().build(conn, project_id=project_id, chapter_id=chapter_id),
            target_pages,
        )
        self._ensure_recommended_charts(conn, project_id=project_id, chapter=chapter, context=context)
        context = with_target_pages_override(
            TechnicalChapterContextBuilder().build(conn, project_id=project_id, chapter_id=chapter_id),
            target_pages,
        )
        context = _with_effective_prompt_template(context)
        ai_result = _request_ai_gateway_completion(context, rewrite_note=rewrite_note)
        if ai_result is not None:
            draft = _save_chapter_draft(
                conn,
                project_id=project_id,
                chapter=chapter,
                content_md=ai_result["content"],
                context=context,
            )
            generation_mode = "ai_gateway"
            ai_metadata = _ai_gateway_metadata(ai_result)
        else:
            draft = generate_bid_chapter_draft(conn, project_id=project_id, chapter_id=chapter_id, context=context, rewrite_note=rewrite_note)
            generation_mode = "deterministic_strategy_fallback"
            ai_metadata = None
        self_check = self._self_check(draft.get("content_md") or "")
        metadata = {
            "chapter_code": chapter["chapter_code"],
            "self_check": self_check,
            "context_hash": _context_hash(context),
            "prompt_version": "technical_chapter_context_v1",
            "prompt_contract": _technical_prompt_contract(context),
            "source_trace": _source_trace(context),
            "generation_mode": generation_mode,
            "prompt_template": _prompt_template_trace(context),
        }
        if ai_metadata is not None:
            metadata["ai_gateway"] = ai_metadata
        run = self._create_run(
            conn,
            project_id=project_id,
            outline_id=outline["id"],
            chapter_id=chapter_id,
            status="completed",
            created_by=created_by,
            prompt_inputs=context,
            metadata=metadata,
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
                    chapter_code=chapter.get("chapter_code"),
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
            "10.1.1 编制依据与质量目标",
            "10.1.2 质量管理标准和规范",
            "10.1.3 质量保证体系与组织职责",
            "10.1.4 全过程质量控制措施",
            "10.1.5 质量管理制度",
            "10.1.6 施工过程质量控制",
            "10.1.7 质量通病防治措施",
            "10.1.8 送电前质量专项检查",
            "10.1.9 质量问题处置和持续改进",
            "10.1.10 质量资料同步管理",
            "10.1.11 业主、监理、运行单位协同验收机制",
            "10.1.12 质量履约评价保障措施",
            "10.1.13 质量管理创新与亮点措施",
            "10.1.14 数字化质量追溯系统应用",
            "10.1.15 地域特殊质量保证措施",
            "10.2.1 安全与绿色施工目标响应",
            "10.2.2 安全管理体系与组织职责",
            "10.2.3 安全管理制度体系",
            "10.2.4 危险源辨识与风险分级管控",
            "10.2.5 施工过程安全保障措施",
            "10.2.6 专项安全技术措施",
            "10.2.7 应急预案体系与响应机制",
            "10.2.8 安全教育培训与班组安全管理",
            "10.2.9 数字化安全管控手段",
            "10.2.10 绿色施工总体目标与管理体系",
            "10.2.11 环境保护与文明施工措施",
            "10.2.12 节材、节水、节能与节地措施",
            "10.2.13 碳排放管理与碳足迹核算",
            "10.2.14 职业健康与劳动保护",
            "10.2.15 安全绿色履约评价保障",
            "10.2.16 地域特殊安全与绿色施工措施",
            "10.3.1 编制依据与进度目标",
            "10.3.2 进度管理体系与组织职责",
            "10.3.3 工期约束与关键假设",
            "10.3.4 施工阶段划分与流水组织",
            "10.3.5 总体施工进度计划",
            "10.3.6 关键路径与节点控制",
            "10.3.7 资源配置与进度匹配",
            "10.3.8 材料设备供应进度保障",
            "10.3.9 停电窗口与外部协调保障",
            "10.3.10 进度动态管控与预警纠偏",
            "10.3.11 延误风险识别与应急赶工",
            "10.3.12 质量安全环保与进度协同",
            "10.3.13 数字化进度管理与资料留痕",
            "10.3.14 框架项目多项目进度协调",
            "10.3.15 地域特殊进度保障措施",
            "项目组织架构",
            "关键岗位配置",
            "职责分工与协同机制",
            "施工总体部署",
            "关键施工流程",
            "8.1 编制依据与标准",
            "8.2 工程概况与施工重难点分析",
            "8.3 施工组织与部署",
            "8.4 主要施工方法及技术要求",
            "8.5 质量管理体系与措施",
            "8.6 安全管理体系与措施",
            "8.7 施工进度计划与保障",
            "8.8 环境保护、绿色低碳与碳足迹管理",
            "8.9 科技创新与智能化应用",
            "8.10 地域特性专题方案",
            "8.11 竣工验收与数字化移交",
            "8.12 售后服务、培训及增值服务",
            "8.13 拟投入施工车辆、机具、工器具、检测设备、安全工器具及设施",
            "8.14 施工项目部组织架构创新设计",
            "8.15 国网年度框架施工工程投标其他创新内容",
            "9.1 项目理解与总体工作思路",
            "9.2 工作目标分解与任务策划",
            "9.3 项目管理组织与制度规划",
            "9.4 协调配合工作规划",
            "9.5 技术管理与创新应用规划",
            "9.6 风险防控与应急管理规划",
            "9.7 履约创优与标准化管理规划",
            "9.8 跨章节协同与边界管理",
        )
        strategy_section_count = sum(1 for heading in strategy_headings if _has_heading(content, heading))
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
                    Jsonb(_json_safe(prompt_inputs or {"source": "confirmed_outline_and_mapped_requirements"})),
                    Jsonb(_json_safe(metadata)),
                    created_by,
                ),
            ).fetchone()
        conn.commit()
        return dict(row) if row else {}


__all__ = ["TechnicalBidWriter"]


def _request_ai_gateway_completion(context: dict[str, Any], *, rewrite_note: str | None = None) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.ai_gateway_url:
        return None
    payload = {
        "task_type": "generate_section",
        "messages": _ai_gateway_messages(context, rewrite_note=rewrite_note),
        "temperature": 0.2,
        "max_tokens": _ai_gateway_max_tokens(context),
        "stream": False,
    }
    request = urllib.request.Request(
        settings.ai_gateway_url.rstrip("/") + "/api/ai/chat",
        data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
        headers={"Content-Type": "application/json", **ai_gateway_headers()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(settings.standard_ai_gateway_timeout_seconds, 300.0)) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        return None
    content = str(result.get("content") or "").strip()
    if not content or content.startswith("[AI Gateway stub"):
        return None
    return {
        "content": content,
        "resolved_model": result.get("resolved_model"),
        "resolved_provider": result.get("resolved_provider"),
        "used_fallback": bool(result.get("used_fallback")),
        "finish_reason": result.get("finish_reason"),
        "usage": {
            "input_tokens": int(result.get("input_tokens") or 0),
            "output_tokens": int(result.get("output_tokens") or 0),
            "reasoning_tokens": int(result.get("reasoning_tokens") or 0),
            "prompt_cache_hit_tokens": int(result.get("prompt_cache_hit_tokens") or 0),
            "prompt_cache_miss_tokens": int(result.get("prompt_cache_miss_tokens") or 0),
            "latency_ms": int(result.get("latency_ms") or 0),
        },
    }


def _ai_gateway_messages(context: dict[str, Any], *, rewrite_note: str | None = None) -> list[dict[str, str]]:
    prompt_template = context.get("prompt_template") if isinstance(context.get("prompt_template"), dict) else {}
    template_content = str(prompt_template.get("effective_content_md") or prompt_template.get("content_md") or "").strip()
    contract = _technical_prompt_contract(context)
    source_context = {
        key: context.get(key)
        for key in contract["allowed_context_keys"]
        if key in context
    }
    user_payload = {
        "task": "generate_technical_bid_chapter",
        "chapter": context.get("chapter"),
        "rewrite_note": rewrite_note,
        "prompt_template": template_content,
        "prompt_contract": contract,
        "source_trace": _source_trace(context),
        "context": source_context,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是投标文件技术标章节编写助手。只根据用户提供的结构化上下文、模板提示词、"
                "已确认招标约束、标准条文、企业资料和图表占位符编写，不得编造未给出的日期、"
                "数量、人员姓名、证书编号、设备型号、金额或承诺。输出 Markdown 正文，保留章节编号，"
                "需要图表的位置必须使用 {{chart:key}} 占位符。不得输出思考过程、说明或 JSON。"
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
    ]


def _ai_gateway_max_tokens(context: dict[str, Any]) -> int:
    controls = context.get("generation_controls") if isinstance(context.get("generation_controls"), dict) else {}
    target_pages = controls.get("target_pages")
    if isinstance(target_pages, int) and target_pages >= 80:
        return 32768
    if isinstance(target_pages, int) and target_pages >= 40:
        return 24576
    return 16384


def _ai_gateway_metadata(ai_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolved_model": ai_result.get("resolved_model"),
        "resolved_provider": ai_result.get("resolved_provider"),
        "used_fallback": bool(ai_result.get("used_fallback")),
        "finish_reason": ai_result.get("finish_reason"),
        "usage": ai_result.get("usage") or {},
    }


def _save_chapter_draft(
    conn: Connection,
    *,
    project_id: UUID,
    chapter: dict[str, Any],
    content_md: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    template_metadata: dict[str, Any] = {}
    try:
        template_inputs = ProjectTemplateInstanceService().build_generation_inputs(conn, project_id=project_id)
        template_metadata = dict(template_inputs.get("metadata") or {})
    except ValueError:
        template_metadata = {}
    referenced_chart_keys = sorted(set(CHART_PLACEHOLDER_RE.findall(content_md)))
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            INSERT INTO chapter_draft (
              id, project_id, volume_type, chapter_code, content_md, referenced_chart_keys,
              template_instance_id, template_revision_no, is_stale_by_template,
              stale_by_template_revision_no, stale_by_template_block_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, NULL, NULL)
            ON CONFLICT (project_id, volume_type, chapter_code)
            DO UPDATE SET
              content_md = EXCLUDED.content_md,
              referenced_chart_keys = EXCLUDED.referenced_chart_keys,
              template_instance_id = EXCLUDED.template_instance_id,
              template_revision_no = EXCLUDED.template_revision_no,
              is_stale_by_template = false,
              stale_by_template_revision_no = NULL,
              stale_by_template_block_id = NULL,
              template_stale_reason = NULL,
              updated_at = now()
            RETURNING *
            """,
            (
                uuid4(),
                project_id,
                chapter.get("volume_type") or "technical",
                chapter["chapter_code"],
                content_md,
                referenced_chart_keys,
                UUID(str(template_metadata["template_instance_id"])) if template_metadata.get("template_instance_id") else None,
                template_metadata.get("template_revision_no"),
            ),
        ).fetchone()
    conn.commit()
    assert row is not None
    return dict(row)


def _context_hash(context: dict[str, Any]) -> str:
    payload = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _has_heading(content: str, heading: str) -> bool:
    return re.search(rf"^\s*#{{2,6}}\s+{re.escape(heading)}(?:\s*$|\s)", content, re.MULTILINE) is not None


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
        "critical_path": "关键路径图",
        "response_matrix": "条款响应矩阵",
        "indicator_table": "指标台账",
        "interface_table": "协调接口表",
        "equipment_table": "设备配置表",
        "closure_flow": "闭环流程图",
        "data_flow": "数据流转图",
    }
    return names.get(chart_type, f"{chapter.get('chapter_title') or '技术章节'}图表")


def _technical_prompt_contract(context: dict[str, Any]) -> dict[str, Any]:
    """Describe the only inputs an AI prose pass may use."""

    strategy = context.get("strategy") if isinstance(context.get("strategy"), dict) else {}
    headings = [
        section.get("heading")
        for section in strategy.get("sections", [])
        if isinstance(section, dict) and section.get("heading")
    ]
    return {
        "version": "technical_chapter_context_v1",
        "input_policy": "normalized_context_and_strategy_only",
        "allowed_context_keys": [
            "chapter",
            "constraint_set",
            "constraints",
            "tender_summary",
            "scoring_items",
            "standard_clauses",
            "personnel_selections",
            "equipment_selections",
            "company_assets",
            "recommended_charts",
            "chart_assets",
            "strategy",
            "prompt_template",
            "generation_controls",
        ],
        "strategy_key": strategy.get("key"),
        "generation_controls": context.get("generation_controls") or {},
        "required_output": {
            "format": "structured_markdown",
            "headings": headings,
            "must_include": [
                "response_matrix",
                "measures",
                "responsibilities",
                "standards_table",
                "chart_placeholders_when_recommended",
            ],
            "trace_metadata": [
                "constraint_ids",
                "standard_clause_ids",
                "scoring_ids",
                "personnel_ids",
                "equipment_ids",
                "chart_placeholder_keys",
            ],
        },
        "forbidden_terms": list(strategy.get("forbidden_terms") or ["报价", "投标报价", "最高限价", "单价", "总价"]),
    }


def _with_effective_prompt_template(context: dict[str, Any]) -> dict[str, Any]:
    prompt_template = context.get("prompt_template")
    if not isinstance(prompt_template, dict):
        return context
    base_content = str(prompt_template.get("content_md") or "").strip()
    overlay = str((context.get("generation_controls") or {}).get("prompt_overlay_md") or "").strip()
    if not overlay:
        return context
    next_context = dict(context)
    next_template = dict(prompt_template)
    next_template["effective_content_md"] = "\n\n".join(part for part in (base_content, overlay) if part)
    next_context["prompt_template"] = next_template
    return next_context


def _prompt_template_trace(context: dict[str, Any]) -> dict[str, Any]:
    prompt_template = context.get("prompt_template") if isinstance(context.get("prompt_template"), dict) else {}
    content = str(prompt_template.get("effective_content_md") or prompt_template.get("content_md") or "")
    return {
        "path": prompt_template.get("path"),
        "status": prompt_template.get("status"),
        "content_length": len(content),
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None,
    }


def _source_trace(context: dict[str, Any]) -> dict[str, list[str]]:
    def ids(rows: Any, key: str = "id") -> list[str]:
        if not isinstance(rows, list):
            return []
        values: list[str] = []
        for row in rows:
            if isinstance(row, dict) and row.get(key):
                values.append(str(row[key]))
        return values

    chart_keys: list[str] = []
    for key in context.get("recommended_charts") or []:
        if key:
            chart_keys.append(str(key))
    for asset in context.get("chart_assets") or []:
        if isinstance(asset, dict) and (asset.get("placeholder_key") or asset.get("chart_type")):
            chart_keys.append(str(asset.get("placeholder_key") or asset.get("chart_type")))

    return {
        "constraint_ids": ids(context.get("constraints")),
        "requirement_ids": ids(context.get("constraints"), "requirement_id"),
        "standard_clause_ids": ids(context.get("standard_clauses"), "id"),
        "scoring_ids": ids(context.get("scoring_items")),
        "personnel_ids": ids(context.get("personnel_selections")),
        "equipment_ids": ids(context.get("equipment_selections")),
        "chart_placeholder_keys": sorted(set(chart_keys)),
    }
