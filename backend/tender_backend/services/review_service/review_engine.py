"""Review engine — rule-based and model-based review of chapter drafts.

Produces review_issue records with severity P0/P1/P2/P3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import structlog
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.services.technical_chapter_strategies import strategy_for_chapter
from tender_backend.services.tender_constraint_service import TenderConstraintService

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ReviewIssue:
    severity: str  # P0, P1, P2, P3
    title: str
    detail: str
    chapter_code: str | None = None
    requirement_id: str | None = None
    metadata_json: dict[str, Any] | None = None


def review_draft(
    *,
    content: str,
    chapter_code: str,
    requirements: list[dict],
    facts: dict[str, str],
) -> list[ReviewIssue]:
    """Run rule-based reviews on a chapter draft."""
    issues: list[ReviewIssue] = []

    # Rule: check veto requirements are addressed
    for req in requirements:
        if req.get("category") == "veto":
            title = req.get("title", "")
            if title and title not in content:
                issues.append(ReviewIssue(
                    severity="P0",
                    title=f"否决项未覆盖: {title[:50]}",
                    detail=f"招标要求中的否决项 '{title}' 在章节 {chapter_code} 中未找到相关内容",
                    chapter_code=chapter_code,
                ))

    # Rule: check facts consistency
    for key, value in facts.items():
        if value and value not in content:
            issues.append(ReviewIssue(
                severity="P2",
                title=f"事实引用不一致: {key}",
                detail=f"项目事实 '{key}={value}' 未出现在章节 {chapter_code} 中",
                chapter_code=chapter_code,
            ))

    # Rule: minimum length check
    if len(content) < 200:
        issues.append(ReviewIssue(
            severity="P1",
            title="章节内容过短",
            detail=f"章节 {chapter_code} 内容仅 {len(content)} 字符，建议至少 200 字",
            chapter_code=chapter_code,
        ))

    generic_phrases = ("严格响应", "完全响应", "按招标文件执行", "满足招标要求")
    strategy = strategy_for_chapter(chapter_code)
    quality_metrics = _chapter_quality_metrics(
        content=content,
        requirements=requirements,
        strategy=strategy,
        generic_phrases=generic_phrases,
    )
    if any(phrase in content for phrase in generic_phrases) and len(content) < 500:
        issues.append(ReviewIssue(
            severity="P1",
            title="章节内容泛化",
            detail="章节以泛化承诺替代具体措施，需补充组织、流程、责任、标准、检查和闭环内容。",
            chapter_code=chapter_code,
            metadata_json={"quality_metrics": quality_metrics},
        ))

    if strategy is not None:
        missing_sections = [heading for heading, _body in strategy.sections if f"## {heading}" not in content]
        if missing_sections:
            issues.append(ReviewIssue(
                severity="P1",
                title="缺少策略必备章节",
                detail="缺少章节：" + "、".join(missing_sections),
                chapter_code=chapter_code,
                metadata_json={"missing_sections": missing_sections, "strategy": strategy.key},
            ))
        missing_charts = [key for key in strategy.required_charts if f"{{{{chart:{key}}}}}" not in content]
        if missing_charts:
            issues.append(ReviewIssue(
                severity="P2",
                title="缺少必备图表占位符",
                detail="缺少图表：" + "、".join(missing_charts),
                chapter_code=chapter_code,
                metadata_json={"missing_charts": missing_charts, "strategy": strategy.key},
            ))
        if strategy.required_standards and not _has_standard_basis(content):
            issues.append(ReviewIssue(
                severity="P1",
                title="缺少标准依据",
                detail="章节未体现标准、规范、验收或国网依据，需补充本地标准库或用户确认的标准条款。",
                chapter_code=chapter_code,
                metadata_json={"required_standards": list(strategy.required_standards), "strategy": strategy.key},
            ))
        issues.extend(_sgcc_domain_issues(content=content, chapter_code=chapter_code))

    unsupported_claims = _unsupported_claims(content)
    if unsupported_claims:
        issues.append(ReviewIssue(
            severity="P1",
            title="存在未支撑承诺",
            detail="章节包含缺少来源或证明支撑的绝对化/领先性表述：" + "、".join(unsupported_claims),
            chapter_code=chapter_code,
            metadata_json={"unsupported_claims": unsupported_claims},
        ))

    if _quality_metrics_block(quality_metrics):
        issues.append(ReviewIssue(
            severity="P1",
            title="章节质量指标不足",
            detail="章节缺少足够的策略章节、约束响应或实质段落，需补充具体措施、责任、标准、检查和闭环内容。",
            chapter_code=chapter_code,
            metadata_json={"quality_metrics": quality_metrics},
        ))

    logger.info("review_completed", chapter_code=chapter_code, issue_count=len(issues))
    return issues


def _chapter_quality_metrics(
    *,
    content: str,
    requirements: list[dict],
    strategy: Any,
    generic_phrases: tuple[str, ...],
) -> dict[str, Any]:
    section_total = len(strategy.sections) if strategy is not None else 0
    section_hit = sum(1 for heading, _body in (strategy.sections if strategy is not None else []) if f"## {heading}" in content)
    covered_requirements = sum(1 for requirement in requirements if _contains_requirement(content, requirement))
    substantive_paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", content)
        if len(paragraph.strip()) >= 40 and not paragraph.strip().startswith("{{chart:")
    ]
    chart_placeholders = re.findall(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}", content)
    generic_hits = sum(content.count(phrase) for phrase in generic_phrases)
    length_units = max(1, len(content) // 200)
    return {
        "required_section_coverage": round(section_hit / section_total, 4) if section_total else 1.0,
        "required_section_count": section_total,
        "covered_required_section_count": section_hit,
        "confirmed_constraint_coverage": round(covered_requirements / len(requirements), 4) if requirements else 1.0,
        "confirmed_constraint_count": len(requirements),
        "covered_confirmed_constraint_count": covered_requirements,
        "chart_placeholder_count": len(set(chart_placeholders)),
        "pricing_term_absent": not any(term in content for term in ("投标报价", "最高限价", "单价", "总价")),
        "generic_phrase_density": round(generic_hits / length_units, 4),
        "substantive_paragraph_count": len(substantive_paragraphs),
        "minimum_substantive_paragraph_count": 3 if strategy is not None else 2,
    }


def _quality_metrics_block(metrics: dict[str, Any]) -> bool:
    return (
        metrics["required_section_coverage"] < 0.7
        or metrics["confirmed_constraint_coverage"] < 0.8
        or metrics["generic_phrase_density"] > 0
        or metrics["substantive_paragraph_count"] < metrics["minimum_substantive_paragraph_count"]
        or not metrics["pricing_term_absent"]
    )


def persist_review_issues(
    conn: Connection,
    *,
    project_id: UUID,
    issues: list[ReviewIssue],
) -> int:
    """Write review issues to the database."""
    count = 0
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM review_issue
            WHERE project_id = %s
              AND resolved = FALSE
              AND COALESCE(lifecycle_status, 'open') NOT IN ('waived_by_user', 'closed')
            """,
            (project_id,),
        )
        for issue in issues:
            cur.execute(
                """
                INSERT INTO review_issue (
                  id, project_id, requirement_id, chapter_code, severity, title, detail, lifecycle_status, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s)
                """,
                (
                    uuid4(),
                    project_id,
                    UUID(issue.requirement_id) if issue.requirement_id else None,
                    issue.chapter_code,
                    issue.severity,
                    issue.title,
                    issue.detail,
                    Jsonb(issue.metadata_json or {}),
                ),
            )
            count += 1
    conn.commit()
    return count


def _contains_requirement(content: str, requirement: dict[str, Any]) -> bool:
    values = [
        str(requirement.get("title") or ""),
        str(requirement.get("requirement_text") or ""),
        str(requirement.get("source_text") or ""),
    ]
    for value in values:
        clean = value.strip()
        if clean and clean in content:
            return True
        tokens = [token for token in clean.replace("，", " ").replace("。", " ").split() if len(token) >= 2]
        if tokens and sum(1 for token in tokens if token in content) >= max(1, len(tokens) // 2):
            return True
    return False


def _has_standard_basis(content: str) -> bool:
    return any(term in content for term in ("标准", "规范", "规程", "验收", "国网", "国家电网"))


def _unsupported_claims(content: str) -> list[str]:
    patterns = ("唯一", "行业第一", "全国领先", "最先进", "零事故", "绝对确保", "100%提前")
    return [pattern for pattern in patterns if pattern in content]


def _sgcc_domain_issues(*, content: str, chapter_code: str) -> list[ReviewIssue]:
    required_terms: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
        "6": (("关键岗位/资格响应不足", ("岗位", "资格|证书")),),
        "8.1": (
            ("编制依据缺少标准条款矩阵", ("标准", "条款", "矩阵")),
        ),
        "8.2": (
            ("重难点分析缺少风险识别", ("风险",)),
            ("重难点分析缺少后续措施索引", ("措施",)),
        ),
        "8.3": (
            ("施工组织部署缺少资源安排", ("资源",)),
            ("施工组织部署缺少协调机制", ("协调",)),
        ),
        "8.4": (
            ("主要施工方法缺少流程或工序控制", ("流程", "工序")),
            ("主要施工方法缺少验收控制", ("验收", "控制")),
            ("主要施工方法缺少风险预控", ("风险", "预控")),
        ),
        "10.1": (
            ("质量措施缺少国网质量要求", ("国网|国家电网",)),
            ("质量措施缺少检查验收闭环", ("检查", "验收", "闭环")),
        ),
        "10.2": (
            ("安全文明施工缺少风险管控", ("风险", "分级", "管控")),
            ("安全文明施工缺少应急响应", ("应急", "响应")),
        ),
        "10.3": (
            ("进度措施缺少里程碑或关键路径", ("里程碑", "关键路径")),
            ("进度措施缺少预警纠偏", ("预警", "纠偏")),
        ),
    }
    issues: list[ReviewIssue] = []
    for title, terms in required_terms.get(chapter_code, ()):
        if not _content_satisfies(content, terms):
            issues.append(ReviewIssue(
                severity="P1",
                title=title,
                detail="章节未覆盖国网工程技术标该主题的关键响应要素。",
                chapter_code=chapter_code,
                metadata_json={"required_terms": list(terms)},
            ))
    return issues


def _content_satisfies(content: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        alternatives = tuple(part for part in term.split("|") if part)
        if alternatives and not any(part in content for part in alternatives):
            return False
    return True


def build_project_review(conn: Connection, *, project_id: UUID) -> list[ReviewIssue]:
    """Review the full bid draft against requirements, matches, and outline."""
    constraint_set = TenderConstraintService().latest_confirmed(conn, project_id=project_id)
    with conn.cursor(row_factory=dict_row) as cur:
        if constraint_set:
            requirements = _requirements_from_constraint_set(constraint_set)
        else:
            requirements = cur.execute(
                """
                SELECT *
                FROM project_requirement
                WHERE project_id = %s
                  AND COALESCE(ignored_for_pricing, false) = false
                  AND COALESCE(is_stale, false) = false
                  AND COALESCE(review_status, 'pending') <> 'rejected'
                ORDER BY category, created_at
                """,
                (project_id,),
            ).fetchall()
        drafts = cur.execute(
            "SELECT chapter_code, content_md, is_stale, stale_reason FROM chapter_draft WHERE project_id = %s",
            (project_id,),
        ).fetchall()
        chapters = cur.execute(
            "SELECT chapter_code, chapter_title, volume_type, sort_order FROM bid_chapter WHERE project_id = %s ORDER BY sort_order",
            (project_id,),
        ).fetchall()
        if constraint_set:
            mapped = _mapped_rows_from_constraints(requirements)
            matches = []
        else:
            mapped = cur.execute(
                """
                SELECT bcr.requirement_id, bc.chapter_code
                FROM bid_chapter_requirement bcr
                JOIN bid_chapter bc ON bc.id = bcr.bid_chapter_id
                WHERE bc.project_id = %s
                """,
                (project_id,),
            ).fetchall()
            matches = cur.execute(
                """
                SELECT rm.*, pr.category, pr.title AS requirement_title
                FROM requirement_match rm
                JOIN project_requirement pr ON pr.id = rm.requirement_id
                WHERE pr.project_id = %s
                """,
                (project_id,),
            ).fetchall()
        chart_assets = cur.execute(
            """
            SELECT placeholder_key, chart_type, status
            FROM chart_asset
            WHERE project_id = %s
            """,
            (project_id,),
        ).fetchall()

    content_by_chapter = {row["chapter_code"]: row["content_md"] for row in drafts}
    all_content = "\n".join(content_by_chapter.values())
    mapped_by_requirement: dict[str, list[str]] = {}
    for row in mapped:
        mapped_by_requirement.setdefault(str(row["requirement_id"]), []).append(row["chapter_code"])

    issues: list[ReviewIssue] = []
    for draft in drafts:
        if draft.get("is_stale"):
            issues.append(
                ReviewIssue(
                    severity="P1",
                    title="章节草稿上下文已过期",
                    detail=draft.get("stale_reason") or "后续澄清、约束或目录变化后，章节草稿需要重新生成或复核。",
                    chapter_code=draft.get("chapter_code"),
                    metadata_json={"stale": True},
                )
            )
    hard_categories = {"veto", "qualification", "performance", "project_team", "technical", "scoring", "special", "format"}
    severity_by_category = {
        "veto": "P0",
        "qualification": "P1",
        "performance": "P1",
        "project_team": "P1",
        "technical": "P1",
        "scoring": "P1",
        "special": "P1",
        "format": "P2",
    }
    for requirement in requirements:
        requirement_id = str(requirement["id"])
        category = requirement.get("category")
        codes = mapped_by_requirement.get(requirement_id, [])
        if (requirement.get("is_veto") or requirement.get("is_hard_constraint") or category in hard_categories) and not codes:
            issues.append(
                ReviewIssue(
                    severity="P0" if requirement.get("is_veto") else "P1",
                    title=f"硬约束未映射章节: {requirement.get('title')}",
                    detail="该招标约束尚未映射到投标响应章节，不能进入最终交付。",
                    requirement_id=requirement_id,
                    metadata_json={"category": category},
                )
            )
            continue
        target_content = "\n".join(content_by_chapter.get(code, "") for code in codes) if codes else all_content
        if category in hard_categories and not _contains_requirement(target_content, requirement):
            issues.append(
                ReviewIssue(
                    severity=severity_by_category.get(str(category), "P2"),
                    title=f"约束未覆盖: {requirement.get('title')}",
                    detail="章节草稿中未找到该约束的明确响应内容。",
                    chapter_code=codes[0] if codes else None,
                    requirement_id=requirement_id,
                    metadata_json={"category": category, "mapped_chapters": codes},
                )
            )

    for row in matches:
        if row["match_status"] in {"missing", "needs_review"}:
            issues.append(
                ReviewIssue(
                    severity="P1" if row.get("category") in {"qualification", "performance", "project_team"} else "P2",
                    title=f"资料缺失或需复核: {row.get('requirement_title')}",
                    detail=row.get("missing_reason") or "知识库匹配结果未满足该约束，需补充或人工确认。",
                    requirement_id=str(row["requirement_id"]),
                    metadata_json={"match_status": row["match_status"], "source_type": row.get("matched_source_type")},
                )
            )

    if chapters:
        sort_orders = [row["sort_order"] for row in chapters]
        if sort_orders != sorted(sort_orders):
            issues.append(ReviewIssue(severity="P2", title="章节顺序异常", detail="投标目录章节排序不连续或不符合当前目录草案。"))
        for volume in ("qualification", "business", "technical"):
            if not any(row["volume_type"] == volume for row in chapters):
                issues.append(ReviewIssue(severity="P2", title=f"缺少{volume}分册", detail=f"投标目录中未找到 {volume} 分册。"))
    else:
        issues.append(ReviewIssue(severity="P1", title="缺少投标目录", detail="尚未生成投标文件目录草案。"))

    if any(term in all_content for term in ("投标报价", "最高限价", "单价", "总价")):
        issues.append(ReviewIssue(severity="P1", title="正文包含报价相关内容", detail="投标正文中出现报价关键词，需移至报价文件或删除。"))

    referenced_charts = set(re.findall(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}", all_content))
    asset_status = {row.get("placeholder_key") or row.get("chart_type"): row.get("status") for row in chart_assets}
    for key in sorted(referenced_charts):
        if asset_status.get(key) != "approved":
            issues.append(
                ReviewIssue(
                    severity="P1",
                    title="引用图表未审批",
                    detail=f"正文引用图表 {key}，但图表尚未审批。",
                    metadata_json={"placeholder_key": key, "status": asset_status.get(key)},
                )
            )

    logger.info("project_review_built", project_id=str(project_id), issue_count=len(issues))
    return issues


def _requirements_from_constraint_set(constraint_set: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in constraint_set.get("items") or []:
        metadata = item.get("metadata_json") or {}
        rows.append(
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "constraint_subtype": item.get("constraint_subtype") or metadata.get("constraint_subtype"),
                "title": item.get("title"),
                "requirement_text": item.get("constraint_text") or "",
                "source_text": item.get("constraint_text") or "",
                "is_veto": item.get("category") == "veto",
                "is_hard_constraint": item.get("confirmation_level") == "critical",
                "source_metadata": metadata,
            }
        )
    return rows


def _mapped_rows_from_constraints(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        metadata = requirement.get("source_metadata") or {}
        codes = list(metadata.get("mapped_chapter_codes") or [])
        if metadata.get("mapped_chapter_code"):
            codes.append(metadata["mapped_chapter_code"])
        for code in dict.fromkeys(str(value) for value in codes if value):
            rows.append({"requirement_id": requirement["id"], "chapter_code": code})
    return rows


def get_blocking_issues(conn: Connection, *, project_id: UUID) -> list[dict]:
    """Get unresolved P0/P1 issues that block export."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT * FROM review_issue
            WHERE project_id = %s
              AND severity IN ('P0', 'P1')
              AND resolved = FALSE
              AND COALESCE(lifecycle_status, 'open') NOT IN ('waived_by_user', 'closed')
            ORDER BY severity, created_at
            """,
            (project_id,),
        ).fetchall()
    return rows
