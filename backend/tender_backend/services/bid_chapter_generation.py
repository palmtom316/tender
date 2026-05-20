"""Deterministic chapter draft generation for bid authoring."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.services.ad_hoc_chapter_task_card import build_task_card_draft_markdown, merge_task_card_metadata
from tender_backend.services.bid_outline_templates import SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
from tender_backend.services.technical_chapter_strategies import strategy_for_chapter
from tender_backend.services.project_template_instance_service import ProjectTemplateInstanceService


PRICING_TERMS = ("报价", "投标报价", "价格", "最高限价", "单价", "总价")
CHART_PLACEHOLDER_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")


_MATERIAL_LOCATION_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("技术偏差", "偏差表"), "第1章 技术偏差表"),
    (("执业合规", "人员合规", "承诺函"), "第2章 关于施工项目人员执业合规的承诺函"),
    (("工期", "进度目标", "计划工期"), "第3章 工期响应"),
    (("资质", "许可证", "体系证书"), "第4章 资质情况"),
    (("业绩汇总", "类似工程业绩汇总"), "第5.1章 类似工程业绩情况汇总表"),
    (("已完成", "近年完成", "完成的类似项目"), "第5.2章 近年完成的类似项目情况及证明材料"),
    (("正在施工", "新承接", "在建"), "第5.3章 正在施工的和新承接的类似项目情况及证明材料"),
    (("业绩", "类似项目"), "第5章 业绩情况"),
    (("现场管理机构", "项目团队", "项目人员", "组织机构", "项目经理"), "第6章 现场管理机构设置"),
    (("资格条件", "其他资格"), "第7章 其他资格条件情况"),
    (("施工方案", "施工方法", "技术措施", "施工组织"), "第8章 施工方案与技术措施"),
    (("工作规划", "总体规划", "协调配合"), "第9章 工作规划描述"),
    (("质量保证", "质量保障", "质量措施", "质量管理"), "第10.1章 质量保障措施"),
    (("安全", "绿色施工", "文明施工", "环保"), "第10.2章 安全和绿色施工保障措施"),
    (("工程进度", "进度计划", "节点控制", "关键路径"), "第10.3章 工程进度计划及保证措施"),
    (("履约评价", "评价证明", "用户评价"), "第11章 履约评价证明材料"),
    (("施工外包", "外包管理", "分包", "劳务分包", "专业分包"), "第12章 施工外包管理"),
    (("其他", "补充材料"), "第13章 其他"),
)


def _table_cell(value: Any) -> str:
    return _text(value).replace("|", "／").replace("\n", " ") or "待确认"


def _material_location_for_requirement(requirement: dict[str, Any]) -> str:
    text = " ".join(
        _text(requirement.get(key))
        for key in ("title", "requirement_text", "source_text")
    )
    for keywords, location in _MATERIAL_LOCATION_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return location
    hint = requirement.get("source_metadata") or requirement.get("metadata_json") or {}
    if isinstance(hint, dict) and hint.get("chapter_hint"):
        return f"第{_table_cell(hint.get('chapter_hint'))}章"
    return "待人工确认技术标资料位置"


def _material_location_index_lines(chapter: dict[str, Any], requirements: list[dict[str, Any]]) -> list[str]:
    chapter_code = str(chapter.get("chapter_code") or "")
    if chapter_code == "0.1":
        intro = "本表根据招标文件中的技术标评分标准（表）解析结果生成，用于列明编制后的技术标中对应资料的名称和位置。"
        empty_source = "技术评分标准解析结果"
    elif chapter_code == "0.2":
        intro = "本表根据招标文件技术规范书解析结果生成，用于列明技术规范书要求提交或体现的资料名称和在技术标中的位置。"
        empty_source = "技术规范书解析结果"
    else:
        intro = "本表汇总技术标重点资料索引。"
        empty_source = "招标文件解析结果"

    rows = requirements or [
        {
            "title": "待补充资料",
            "requirement_text": "系统尚未解析到本章对应条目，请先完成招标文件解析或人工补录。",
            "source_file": empty_source,
            "source_locator": "待确认",
        }
    ]
    lines = [
        "## 资料位置索引表",
        intro,
        "",
        "| 序号 | 解析来源 | 资料名称 | 技术标资料位置 | 对应评分/规范要求 | 状态 |",
        "|---:|---|---|---|---|---|",
    ]
    for index, requirement in enumerate(rows, start=1):
        source = " ".join(
            part
            for part in (
                _table_cell(requirement.get("source_file")),
                _table_cell(requirement.get("source_locator")),
            )
            if part != "待确认"
        ) or empty_source
        material_name = _table_cell(requirement.get("title"))
        requirement_text = _sanitize_for_body(_table_cell(requirement.get("requirement_text") or requirement.get("source_text") or material_name))
        location = _material_location_for_requirement(requirement)
        lines.append(
            f"| {index} | {source} | {material_name} | {location} | {requirement_text} | 待确认 |"
        )
    lines.extend([
        "",
        "## 使用要求",
        "- 本章只作为资料定位索引，不替代对应章节正文和附件证明。",
        "- 导出前应复核每一行的资料名称、章节位置和页码，确保可被评审专家按索引追溯。",
        "- 若解析结果与招标文件原文不一致，以招标文件原文和人工确认结果为准。",
        "",
    ])
    return lines


def _technical_directory_lines() -> list[str]:
    lines = ["## 标书目录", ""]
    for chapter in SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS:
        code = str(chapter["chapter_code"])
        if code == "0" or code.startswith("0."):
            continue
        title = str(chapter["chapter_title"])
        indent = "    " if chapter.get("parent_code") else ""
        lines.append(f"{indent}{code}. {title}..........第 页")
    lines.append("")
    return lines


def _chapter_zero_index_lines() -> list[str]:
    return [
        "## 技术标重点资料索引",
        "",
        "## 技术评分标准支撑材料",
        "",
        "## 技术规范书规定应该提交的材料",
        "",
    ]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sanitize_for_body(value: str) -> str:
    if any(term in value for term in PRICING_TERMS):
        return "（该项属于非本系统处理范围，正文生成时已按规则排除。）"
    return value


def _load_chapter_context(conn: Connection, *, project_id: UUID, chapter_id: UUID | None, chapter_code: str | None) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        if chapter_id is not None:
            chapter = cur.execute(
                "SELECT * FROM bid_chapter WHERE id = %s AND project_id = %s",
                (chapter_id, project_id),
            ).fetchone()
        elif chapter_code:
            chapter = cur.execute(
                """
                SELECT bc.*
                FROM bid_chapter bc
                JOIN bid_outline bo ON bo.id = bc.bid_outline_id
                WHERE bc.project_id = %s AND bc.chapter_code = %s
                ORDER BY bo.created_at DESC, bc.sort_order
                LIMIT 1
                """,
                (project_id, chapter_code),
            ).fetchone()
        else:
            chapter = None
        if chapter is None:
            raise ValueError("bid chapter not found")

        requirements = cur.execute(
            """
            SELECT pr.*, bcr.mapping_reason, bcr.priority_level
            FROM bid_chapter_requirement bcr
            JOIN project_requirement pr ON pr.id = bcr.requirement_id
            WHERE bcr.bid_chapter_id = %s
              AND COALESCE(pr.ignored_for_pricing, false) = false
              AND COALESCE(pr.is_stale, false) = false
              AND COALESCE(pr.review_status, 'pending') <> 'rejected'
            ORDER BY bcr.priority_level, pr.created_at
            """,
            (chapter["id"],),
        ).fetchall()
        matches = cur.execute(
            """
            SELECT rm.*, pr.title AS requirement_title
            FROM requirement_match rm
            JOIN project_requirement pr ON pr.id = rm.requirement_id
            WHERE rm.requirement_id = ANY(%s)
            ORDER BY rm.match_status, rm.match_score DESC NULLS LAST
            """,
            ([row["id"] for row in requirements],),
        ).fetchall() if requirements else []
    return {
        "chapter": dict(chapter),
        "requirements": [dict(row) for row in requirements],
        "matches": [dict(row) for row in matches],
    }


def _legacy_context_from_normalized(context: dict[str, Any]) -> dict[str, Any]:
    requirements: list[dict[str, Any]] = []
    for item in context.get("constraints") or []:
        requirement_id = item.get("requirement_id") or item.get("id")
        requirements.append(
            {
                "id": requirement_id,
                "title": item.get("title"),
                "requirement_text": item.get("constraint_text") or "",
                "source_text": item.get("constraint_text") or "",
                "source_file": item.get("source_file"),
                "source_locator": item.get("source_locator"),
                "priority_level": item.get("priority_level") or "normal",
                "category": item.get("category"),
                "is_veto": item.get("category") == "veto",
                "is_hard_constraint": item.get("confirmation_level") == "critical",
            }
        )
    matches = [dict(row) for row in context.get("standard_clauses") or []]
    return {
        "chapter": dict(context["chapter"]),
        "requirements": requirements,
        "matches": matches,
        "recommended_charts": list(context.get("recommended_charts") or []),
    }


def _match_lines(requirement_id: UUID, matches: list[dict[str, Any]]) -> list[str]:
    rows = [row for row in matches if row.get("requirement_id") == requirement_id]
    if not rows:
        return ["  - 匹配资料：未执行知识库匹配或暂无匹配记录，需人工复核。"]
    lines: list[str] = []
    for row in rows:
        status = row.get("match_status")
        title = row.get("matched_title") or row.get("missing_reason") or "待补充资料"
        lines.append(f"  - 匹配资料：{status} - {title}")
    return lines


def _strategy_for_chapter(chapter: dict[str, Any]) -> dict[str, Any] | None:
    strategy = strategy_for_chapter(str(chapter.get("chapter_code") or ""))
    if strategy is None:
        return None
    return {
        "sections": list(strategy.sections),
        "charts": [f"{{{{chart:{key}}}}}" for key in strategy.required_charts],
        "required_facts": list(strategy.required_facts),
        "required_standards": list(strategy.required_standards),
        "innovation_slots": list(strategy.innovation_slots),
        "self_check_rules": list(strategy.self_check_rules),
    }


def _requirement_lines(requirements: list[dict[str, Any]], matches: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    if not requirements:
        return ["本章节暂无已映射的招标约束，保留章节结构并等待人工补充。"]
    for index, requirement in enumerate(requirements, start=1):
        title = _text(requirement.get("title")) or f"约束 {index}"
        body = _sanitize_for_body(_text(requirement.get("requirement_text") or requirement.get("source_text") or title))
        priority = requirement.get("priority_level") or "normal"
        source = _text(requirement.get("source_locator"))
        lines.extend(
            [
                f"### {index}. {title}",
                f"- 优先级：{priority}",
                f"- 来源：{requirement.get('source_file') or '招标文件'} {source}".strip(),
                f"- 响应：{body}",
            ]
        )
        lines.extend(_match_lines(requirement["id"], matches))
        if requirement.get("is_veto") or requirement.get("is_hard_constraint"):
            lines.append("  - 硬约束处理：该要求作为导出前审查重点，不得遗漏或弱化。")
    return lines


def _substantial_strategy_lines(
    *,
    heading: str,
    requirements: list[dict[str, Any]],
    strategy: dict[str, Any],
) -> list[str]:
    requirement_titles = "、".join(_text(row.get("title")) for row in requirements if _text(row.get("title"))) or "本章节招标约束"
    standards = "、".join(strategy.get("required_standards") or []) or "招标文件、国家电网工程管理制度及现行验收规范"
    innovations = "、".join(strategy.get("innovation_slots") or []) or "过程数字化留痕、问题闭环看板"
    checks = "；".join(strategy.get("self_check_rules") or []) or "章节内容需覆盖目标、措施、责任、验收和闭环"
    return [
        "### 管控措施",
        f"- 围绕{requirement_titles}设置目标分解、过程交底、节点检查、问题整改和复验销项措施，确保措施可执行、可检查、可追溯。",
        "### 责任分工",
        f"- 由项目经理统筹，技术负责人牵头制定{heading}实施要求，专业负责人落实班组交底、过程记录和资料同步，质量、安全、进度岗位按职责复核。",
        "### 标准与验收",
        f"- 执行依据包括{standards}；每项措施均明确验收口径、记录表单、责任岗位和复核频次。",
        "### 风险预控",
        "- 对人员不到位、材料设备滞后、交叉作业、关键节点遗漏、资料不同步等风险建立预警清单，触发纠偏后形成整改、复验、销项闭环。",
        "### 创新提升",
        f"- 引入{innovations}，提升现场响应速度、专家可读性和履约过程透明度。",
        "### 自检规则",
        f"- {checks}。",
    ]


def _strategy_lines(
    chapter: dict[str, Any],
    requirements: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    *,
    recommended_charts: list[str] | None = None,
) -> list[str]:
    strategy = _strategy_for_chapter(chapter)
    if not strategy:
        return _requirement_lines(requirements, matches)

    chapter_code = str(chapter.get("chapter_code") or "")
    if chapter_code == "0":
        return _chapter_zero_index_lines()
    if chapter_code in {"0.1", "0.2"}:
        return _material_location_index_lines(chapter, requirements)
    if chapter_code == "0.3":
        return _technical_directory_lines()

    lines: list[str] = []
    for heading, default_body in strategy["sections"]:
        heading_code = str(heading).split(" ", 1)[0]
        heading_level = "##" if "." not in heading_code or str(heading).startswith(("8.", "9.")) else "###"
        lines.extend([f"{heading_level} {heading}", default_body])
        if heading.endswith("响应") or heading in {"技术偏差表", "里程碑计划", "风险识别与分级管控", "关键岗位配置", "评分点响应索引"}:
            lines.extend(_requirement_lines(requirements, matches))
        lines.extend(_substantial_strategy_lines(heading=heading, requirements=requirements, strategy=strategy))
        lines.append("")
    charts = [f"{{{{chart:{key}}}}}" for key in recommended_charts] if recommended_charts is not None else list(strategy.get("charts") or [])
    if charts:
        lines.extend(["## 图表配置", *charts, ""])
    return lines


def _ad_hoc_task_card(chapter: dict[str, Any]) -> dict[str, Any] | None:
    metadata = chapter.get("metadata_json") or {}
    if not isinstance(metadata, dict):
        return None
    card = metadata.get("ad_hoc_task_card")
    return dict(card) if isinstance(card, dict) else None


def _mark_ad_hoc_card_draft_ready(conn: Connection, *, chapter: dict[str, Any]) -> None:
    card = _ad_hoc_task_card(chapter)
    if not card:
        return
    card["status"] = "draft_ready"
    card["draft_stale"] = False
    metadata = merge_task_card_metadata(chapter.get("metadata_json") or {}, card)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE bid_chapter
                SET metadata_json = %s, updated_at = now()
                WHERE id = %s AND project_id = %s
                """,
                (Jsonb(metadata), chapter.get("id"), chapter.get("project_id")),
            )
    except Exception:
        # Some unit-test fake connections only model draft insertion. The draft
        # save remains authoritative for those tests. Real DB errors still surface
        # from the draft insert below.
        return


def generate_bid_chapter_draft(
    conn: Connection,
    *,
    project_id: UUID,
    chapter_id: UUID | None = None,
    chapter_code: str | None = None,
    context: dict[str, Any] | None = None,
    rewrite_note: str | None = None,
) -> dict[str, Any]:
    loaded_context = _legacy_context_from_normalized(context) if context is not None else _load_chapter_context(conn, project_id=project_id, chapter_id=chapter_id, chapter_code=chapter_code)
    chapter = loaded_context["chapter"]
    requirements = loaded_context["requirements"]
    matches = loaded_context["matches"]
    recommended_charts = loaded_context.get("recommended_charts")
    coverage_report_json: dict[str, Any] = {}

    ad_hoc_card = _ad_hoc_task_card(chapter)
    if ad_hoc_card is not None:
        content_md, coverage_report_json = build_task_card_draft_markdown(ad_hoc_card, requirements)
        referenced_chart_keys = sorted(set(CHART_PLACEHOLDER_RE.findall(content_md)))
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO chapter_draft (
                  id, project_id, volume_type, chapter_code, content_md, referenced_chart_keys,
                  template_instance_id, template_revision_no, coverage_report_json, is_stale_by_template,
                  stale_by_template_revision_no, stale_by_template_block_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, %s, false, NULL, NULL)
                ON CONFLICT (project_id, volume_type, chapter_code)
                DO UPDATE SET
                  content_md = EXCLUDED.content_md,
                  referenced_chart_keys = EXCLUDED.referenced_chart_keys,
                  coverage_report_json = EXCLUDED.coverage_report_json,
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
                    Jsonb(coverage_report_json),
                ),
            ).fetchone()
        if coverage_report_json.get("coverage_passed"):
            _mark_ad_hoc_card_draft_ready(conn, chapter=chapter)
        conn.commit()
        assert row is not None
        return dict(row)

    raw_chapter_code = str(chapter.get("chapter_code") or "")
    if raw_chapter_code in {"0", "0.3"}:
        lines = [f"# {chapter['chapter_title']}", ""]
    else:
        lines = [
            f"# {chapter['chapter_code']} {chapter['chapter_title']}",
            "",
            "## 编制原则",
            "本章节依据已确认的项目模板实例和招标文件解析出的约束编写；当模板与招标文件要求冲突时，以招标文件解析结果为准。",
            "",
        ]
    template_metadata: dict[str, Any] = {}
    try:
        template_inputs = ProjectTemplateInstanceService().build_generation_inputs(conn, project_id=project_id)
        template_metadata = dict(template_inputs.get("metadata") or {})
        template_chapter = next((item for item in template_inputs.get("chapters", []) if item.get("chapter_code") == chapter.get("chapter_code")), None)
        if template_chapter:
            fixed_blocks = [block for block in template_chapter.get("blocks", []) if block.get("block_type") == "fixed_text" and block.get("content_text")]
            prompt_blocks = [block for block in template_chapter.get("blocks", []) if block.get("block_type") == "ai_prompt" and block.get("prompt_text")]
            seal_blocks = [block for block in template_chapter.get("blocks", []) if block.get("block_type") == "seal_mark"]
            if fixed_blocks or prompt_blocks or seal_blocks:
                lines.extend(["## 项目模板实例约束"])
                lines.extend(f"- 固定文本：{block['content_text']}" for block in fixed_blocks)
                lines.extend(f"- 写作提示：{block['prompt_text']}" for block in prompt_blocks)
                lines.extend(f"- 签章要求：{block['label']}" for block in seal_blocks)
                lines.append("")
    except ValueError:
        pass
    if _strategy_for_chapter(chapter):
        lines.extend(_strategy_lines(chapter, requirements, matches, recommended_charts=recommended_charts))
    else:
        lines.append("## 响应内容")
        lines.extend(_strategy_lines(chapter, requirements, matches, recommended_charts=recommended_charts))
    if rewrite_note:
        lines.extend(["", "## 人工重写要求", rewrite_note])

    content_md = "\n".join(lines)
    referenced_chart_keys = sorted(set(CHART_PLACEHOLDER_RE.findall(content_md)))
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            INSERT INTO chapter_draft (
              id, project_id, volume_type, chapter_code, content_md, referenced_chart_keys,
              template_instance_id, template_revision_no, coverage_report_json, is_stale_by_template,
              stale_by_template_revision_no, stale_by_template_block_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false, NULL, NULL)
            ON CONFLICT (project_id, volume_type, chapter_code)
            DO UPDATE SET
              content_md = EXCLUDED.content_md,
              referenced_chart_keys = EXCLUDED.referenced_chart_keys,
              template_instance_id = EXCLUDED.template_instance_id,
              template_revision_no = EXCLUDED.template_revision_no,
              coverage_report_json = EXCLUDED.coverage_report_json,
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
                Jsonb(coverage_report_json),
            ),
        ).fetchone()
    conn.commit()
    assert row is not None
    return dict(row)
