"""Review engine — rule-based and model-based review of chapter drafts.

Produces review_issue records with severity P0/P1/P2/P3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import structlog
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

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

    logger.info("review_completed", chapter_code=chapter_code, issue_count=len(issues))
    return issues


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


def build_project_review(conn: Connection, *, project_id: UUID) -> list[ReviewIssue]:
    """Review the full bid draft against requirements, matches, and outline."""
    with conn.cursor(row_factory=dict_row) as cur:
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
            "SELECT chapter_code, content_md FROM chapter_draft WHERE project_id = %s",
            (project_id,),
        ).fetchall()
        chapters = cur.execute(
            "SELECT chapter_code, chapter_title, volume_type, sort_order FROM bid_chapter WHERE project_id = %s ORDER BY sort_order",
            (project_id,),
        ).fetchall()
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

    content_by_chapter = {row["chapter_code"]: row["content_md"] for row in drafts}
    all_content = "\n".join(content_by_chapter.values())
    mapped_by_requirement: dict[str, list[str]] = {}
    for row in mapped:
        mapped_by_requirement.setdefault(str(row["requirement_id"]), []).append(row["chapter_code"])

    issues: list[ReviewIssue] = []
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

    logger.info("project_review_built", project_id=str(project_id), issue_count=len(issues))
    return issues


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
