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

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ReviewIssue:
    severity: str  # P0, P1, P2, P3
    title: str
    detail: str
    chapter_code: str | None = None


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
        for issue in issues:
            cur.execute(
                """
                INSERT INTO review_issue (id, project_id, severity, title, detail)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (uuid4(), project_id, issue.severity, issue.title, issue.detail),
            )
            count += 1
    conn.commit()
    return count


def get_blocking_issues(conn: Connection, *, project_id: UUID) -> list[dict]:
    """Get unresolved P0/P1 issues that block export."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT * FROM review_issue
            WHERE project_id = %s AND severity IN ('P0', 'P1') AND resolved = FALSE
            ORDER BY severity, created_at
            """,
            (project_id,),
        ).fetchall()
    return rows
