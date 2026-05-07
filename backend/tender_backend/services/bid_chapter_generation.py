"""Deterministic chapter draft generation for bid authoring."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


PRICING_TERMS = ("报价", "投标报价", "价格", "最高限价", "单价", "总价")


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
        "## 响应内容",
    ]
    if not requirements:
        lines.append("本章节暂无已映射的招标约束，保留章节结构并等待人工补充。")
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
                f"- 响应：我方将严格响应该要求：{body}",
            ]
        )
        lines.extend(_match_lines(requirement["id"], matches))
        if requirement.get("is_veto") or requirement.get("is_hard_constraint"):
            lines.append("  - 硬约束处理：该要求作为导出前审查重点，不得遗漏或弱化。")
    if rewrite_note:
        lines.extend(["", "## 人工重写要求", rewrite_note])

    content_md = "\n".join(lines)
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            INSERT INTO chapter_draft (id, project_id, chapter_code, content_md)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (project_id, chapter_code)
            DO UPDATE SET content_md = EXCLUDED.content_md, updated_at = now()
            RETURNING *
            """,
            (uuid4(), project_id, chapter["chapter_code"], content_md),
        ).fetchone()
    conn.commit()
    assert row is not None
    return dict(row)
