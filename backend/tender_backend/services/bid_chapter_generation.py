"""Deterministic chapter draft generation for bid authoring."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.services.technical_chapter_strategies import strategy_for_chapter


PRICING_TERMS = ("报价", "投标报价", "价格", "最高限价", "单价", "总价")
CHART_PLACEHOLDER_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")

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

    lines: list[str] = []
    for heading, default_body in strategy["sections"]:
        heading_code = str(heading).split(" ", 1)[0]
        heading_level = "##" if "." not in heading_code or str(heading).startswith(("8.", "9.")) else "###"
        lines.extend([f"{heading_level} {heading}", default_body])
        if heading.endswith("响应") or heading in {"里程碑计划", "风险识别与分级管控", "关键岗位配置", "评分点响应索引"}:
            lines.extend(_requirement_lines(requirements, matches))
        lines.extend(_substantial_strategy_lines(heading=heading, requirements=requirements, strategy=strategy))
        lines.append("")
    charts = [f"{{{{chart:{key}}}}}" for key in recommended_charts] if recommended_charts is not None else list(strategy.get("charts") or [])
    if charts:
        lines.extend(["## 图表配置", *charts, ""])
    return lines


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

    lines = [
        f"# {chapter['chapter_code']} {chapter['chapter_title']}",
        "",
        "## 编制原则",
        "本章节依据招标文件解析出的约束编写；当模板与招标文件要求冲突时，以招标文件解析结果为准。",
        "",
    ]
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
            INSERT INTO chapter_draft (id, project_id, volume_type, chapter_code, content_md, referenced_chart_keys)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (project_id, volume_type, chapter_code)
            DO UPDATE SET
              content_md = EXCLUDED.content_md,
              referenced_chart_keys = EXCLUDED.referenced_chart_keys,
              updated_at = now()
            RETURNING *
            """,
            (uuid4(), project_id, chapter.get("volume_type") or "technical", chapter["chapter_code"], content_md, referenced_chart_keys),
        ).fetchone()
    conn.commit()
    assert row is not None
    return dict(row)
