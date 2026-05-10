"""Deterministic chapter draft generation for bid authoring."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


PRICING_TERMS = ("报价", "投标报价", "价格", "最高限价", "单价", "总价")
CHART_PLACEHOLDER_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")

TECHNICAL_CHAPTER_STRATEGIES: dict[str, dict[str, Any]] = {
    "6": {
        "sections": [
            ("项目组织架构", "建立项目经理负责制，明确技术、质量、安全、进度、资料等岗位职责和接口关系。"),
            ("关键岗位配置", "围绕招标文件人员数量、资格、社保和到岗要求配置管理人员，确保人证岗匹配。"),
            ("职责分工与协同机制", "通过责任矩阵、例会、交底和闭环跟踪机制保障项目团队高效履约。"),
        ],
        "charts": ["{{chart:org_chart}}", "{{chart:responsibility_matrix}}"],
    },
    "8.1": {
        "sections": [
            ("施工总体部署", "结合工程范围、现场条件和国网工程管理要求进行施工区段、工序和资源部署。"),
            ("关键施工流程", "按准备、实施、验收、移交的主线组织工序，明确关键控制点和交接标准。"),
            ("资源投入与现场协调", "统筹人员、机械、材料、停电窗口和外部协调，降低交叉作业风险。"),
        ],
        "charts": ["{{chart:construction_flow}}"],
    },
    "10.1": {
        "sections": [
            ("质量目标响应", "逐项响应招标文件质量目标，确保工程质量、资料质量和验收结果满足国网工程要求。"),
            ("质量管理组织", "建立项目经理牵头、技术负责人主控、专业人员分级负责的质量管理体系。"),
            ("过程质量控制措施", "覆盖材料设备进场、工序交接、隐蔽工程、关键节点验收和资料同步归档。"),
            ("质量检查与闭环改进", "通过自检、互检、专检、问题整改、复验销项形成质量闭环。"),
        ],
        "charts": ["{{chart:quality_system}}"],
    },
    "10.2": {
        "sections": [
            ("安全文明施工目标", "响应安全文明施工和绿色施工要求，落实国网工程安全管理标准。"),
            ("风险识别与分级管控", "识别临电、吊装、高处、交叉作业、消防和交通等风险，形成预控清单。"),
            ("现场文明与绿色施工措施", "控制扬尘、噪声、废弃物、材料堆放和现场标识，保持作业面有序。"),
            ("应急响应与持续改进", "建立应急组织、预案演练、事件报告和复盘改进机制。"),
        ],
        "charts": ["{{chart:safety_system}}", "{{chart:risk_matrix}}"],
    },
    "10.3": {
        "sections": [
            ("里程碑计划", "将总工期分解为准备、施工、调试、验收、移交等里程碑并明确完成标准。"),
            ("关键路径与资源保障", "围绕关键工序配置人员、设备、材料和协调资源，保障连续施工。"),
            ("进度预警与纠偏机制", "建立日跟踪、周分析、节点预警和资源加倍投入等纠偏措施。"),
        ],
        "charts": ["{{chart:schedule_gantt}}"],
    },
    "12": {
        "sections": [
            ("评分点响应索引", "逐项识别技术评分标准并建立章节、资料、证明材料对应关系。"),
            ("支撑材料组织", "按评分维度组织业绩、人员、方案、标准和创新措施证明材料。"),
        ],
        "charts": [],
    },
    "13": {
        "sections": [
            ("技术规范响应范围", "对技术规范书要求逐条确认响应范围、实施措施和验收依据。"),
            ("国网标准符合性措施", "将国网工程施工、质量、安全、资料和验收要求嵌入实施过程。"),
        ],
        "charts": [],
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sanitize_for_body(value: str) -> str:
    if any(term in value for term in PRICING_TERMS):
        return "（该项涉及报价信息，正文生成时已按规则排除，需在报价文件中另行处理。）"
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
    code = str(chapter.get("chapter_code") or "")
    return TECHNICAL_CHAPTER_STRATEGIES.get(code)


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


def _strategy_lines(chapter: dict[str, Any], requirements: list[dict[str, Any]], matches: list[dict[str, Any]]) -> list[str]:
    strategy = _strategy_for_chapter(chapter)
    if not strategy:
        return _requirement_lines(requirements, matches)

    lines: list[str] = []
    for heading, default_body in strategy["sections"]:
        lines.extend([f"## {heading}", default_body])
        if heading.endswith("响应") or heading in {"里程碑计划", "风险识别与分级管控", "关键岗位配置", "评分点响应索引"}:
            lines.extend(_requirement_lines(requirements, matches))
        lines.append("")
    charts = list(strategy.get("charts") or [])
    if charts:
        lines.extend(["## 图表配置", *charts, ""])
    return lines


def generate_bid_chapter_draft(
    conn: Connection,
    *,
    project_id: UUID,
    chapter_id: UUID | None = None,
    chapter_code: str | None = None,
    rewrite_note: str | None = None,
) -> dict[str, Any]:
    context = _load_chapter_context(conn, project_id=project_id, chapter_id=chapter_id, chapter_code=chapter_code)
    chapter = context["chapter"]
    requirements = context["requirements"]
    matches = context["matches"]

    lines = [
        f"# {chapter['chapter_code']} {chapter['chapter_title']}",
        "",
        "## 编制原则",
        "本章节依据招标文件解析出的约束编写；当模板与招标文件要求冲突时，以招标文件解析结果为准。",
        "",
    ]
    if _strategy_for_chapter(chapter):
        lines.extend(_strategy_lines(chapter, requirements, matches))
    else:
        lines.append("## 响应内容")
        lines.extend(_strategy_lines(chapter, requirements, matches))
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
