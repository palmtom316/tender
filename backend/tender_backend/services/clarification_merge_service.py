"""Clarification/addendum impact analysis and stale propagation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.db.repositories.clarification_repo import ClarificationRepository


KEYWORDS_BY_CATEGORY: list[tuple[str, tuple[str, ...]]] = [
    ("veto", ("废标", "否决", "无效投标", "实质性响应")),
    ("qualification", ("资质", "许可证", "资格", "证书", "承装", "承修", "承试")),
    ("performance", ("业绩", "类似工程", "合同", "竣工", "验收")),
    ("project_team", ("项目经理", "技术负责人", "安全员", "人员", "社保")),
    ("format", ("正本", "副本", "份数", "签章", "盖章", "密封", "格式")),
    ("schedule", ("截止", "递交", "开标", "工期", "时间")),
    ("technical", ("技术", "施工方案", "质量", "安全", "进度")),
    ("scoring", ("评分", "分值", "评审")),
    ("business", ("投标函", "商务", "保证金", "保函")),
]

STALE_REVIEW_STATUS = "stale"
CLARIFICATION_EXTRACTION_METHOD = "clarification"


@dataclass(frozen=True)
class ClarificationClause:
    title: str
    text: str
    category: str
    source_locator: str


class ClarificationMergeService:
    """Apply later clarification clauses over earlier tender requirements.

    Later readable clarification/addendum files override matched earlier
    requirements. Affected requirements, outlines, chapters, and existing
    drafts are marked stale so the operator must reconfirm the new clauses
    before downstream generation continues.
    """

    def create_and_apply(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        repo = ClarificationRepository()
        clarification = repo.create(conn, project_id=project_id, fields=fields, commit=False)
        impact = self.apply(conn, project_id=project_id, clarification=clarification, commit=False)
        updated = repo.update_impact(conn, clarification_id=clarification["id"], impact_json=impact, commit=False)
        conn.commit()
        result = updated or clarification
        result["impact_json"] = impact
        return result

    def apply(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        clarification: dict[str, Any],
        commit: bool = True,
    ) -> dict[str, Any]:
        clauses = self.extract_clauses(clarification.get("content_text") or "")
        requirements = self._load_active_requirements(conn, project_id=project_id)
        affected_pairs: list[dict[str, Any]] = []

        with conn.cursor(row_factory=dict_row) as cur:
            for index, clause in enumerate(clauses, start=1):
                matched = self._match_existing_requirement(clause, requirements)
                new_requirement = cur.execute(
                    """
                    INSERT INTO project_requirement (
                      id, project_id, category, title, requirement_text, source_text,
                      source_file, source_locator, confidence, is_veto, is_hard_constraint,
                      requires_human_confirm, ignored_for_pricing, review_status,
                      review_note, source_metadata, human_confirmed, extraction_method
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, false,
                            'pending', %s, %s, false, %s)
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        project_id,
                        clause.category,
                        clause.title,
                        clause.text,
                        clause.text,
                        clarification.get("source_file"),
                        clause.source_locator or f"clarification-round-{clarification.get('round_no')}-{index}",
                        0.95,
                        clause.category == "veto",
                        clause.category in {"veto", "qualification", "performance", "project_team", "format", "schedule"},
                        f"后发{clarification.get('clarification_type') or 'clarification'}覆盖前文，需重新确认。",
                        Jsonb(
                            {
                                "clarification_id": str(clarification["id"]),
                                "clarification_round": clarification.get("round_no"),
                                "supersedes_requirement_id": str(matched["id"]) if matched else None,
                                "override_policy": "later_clarification_overrides_earlier_text",
                            }
                        ),
                        CLARIFICATION_EXTRACTION_METHOD,
                    ),
                ).fetchone()
                if matched and new_requirement:
                    cur.execute(
                        """
                        UPDATE project_requirement
                        SET is_stale = true,
                            stale_reason = %s,
                            stale_by_clarification_id = %s,
                            superseded_by_requirement_id = %s,
                            review_status = %s,
                            human_confirmed = false,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (
                            f"被后发澄清/补遗覆盖：{clause.title}",
                            clarification["id"],
                            new_requirement["id"],
                            STALE_REVIEW_STATUS,
                            matched["id"],
                        ),
                    )
                    affected_pairs.append(
                        {
                            "old_requirement_id": str(matched["id"]),
                            "new_requirement_id": str(new_requirement["id"]),
                            "category": clause.category,
                            "title": clause.title,
                            "similarity": matched.get("_similarity"),
                        }
                    )

            affected_requirement_ids = [UUID(pair["old_requirement_id"]) for pair in affected_pairs]
            stale_chapter_rows = self._mark_dependent_artifacts_stale(
                cur,
                project_id=project_id,
                clarification_id=clarification["id"],
                affected_requirement_ids=affected_requirement_ids,
            )
        if commit:
            conn.commit()

        return {
            "override_policy": "later_clarification_overrides_earlier_text",
            "clarification_id": str(clarification["id"]),
            "created_requirement_count": len(clauses),
            "superseded_requirement_count": len(affected_pairs),
            "affected_pairs": affected_pairs,
            "stale_outline_count": stale_chapter_rows["outline_count"],
            "stale_chapter_count": stale_chapter_rows["chapter_count"],
            "stale_draft_count": stale_chapter_rows["draft_count"],
            "requires_reconfirmation": len(clauses) > 0,
        }

    def extract_clauses(self, content_text: str) -> list[ClarificationClause]:
        chunks = [
            _clean_text(chunk)
            for chunk in re.split(r"(?:\n\s*\n|[；;])", content_text)
            if _clean_text(chunk)
        ]
        clauses: list[ClarificationClause] = []
        for index, chunk in enumerate(chunks, start=1):
            title = self._title(chunk, index=index)
            clauses.append(
                ClarificationClause(
                    title=title,
                    text=chunk,
                    category=self._category(chunk),
                    source_locator=f"clarification-clause-{index}",
                )
            )
        return clauses

    def _load_active_requirements(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT *
                FROM project_requirement
                WHERE project_id = %s
                  AND COALESCE(is_stale, false) = false
                  AND COALESCE(review_status, 'pending') NOT IN ('rejected', 'merged', 'split', 'stale')
                ORDER BY created_at
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _match_existing_requirement(self, clause: ClarificationClause, requirements: list[dict[str, Any]]) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_score = 0.0
        clause_topic = _topic_key(clause.text)
        for row in requirements:
            row_text = _requirement_text(row)
            if not row_text:
                continue
            category_bonus = 0.15 if row.get("category") == clause.category else 0.0
            topic_bonus = 0.2 if clause_topic and clause_topic == _topic_key(row_text) else 0.0
            score = SequenceMatcher(None, _normalise(row_text), _normalise(clause.text)).ratio() + category_bonus + topic_bonus
            if score > best_score:
                best = dict(row)
                best_score = score
        if best is None or best_score < 0.52:
            return None
        best["_similarity"] = round(best_score, 4)
        return best

    def _mark_dependent_artifacts_stale(
        self,
        cur: Any,
        *,
        project_id: UUID,
        clarification_id: UUID,
        affected_requirement_ids: list[UUID],
    ) -> dict[str, int]:
        if not affected_requirement_ids:
            return {"outline_count": 0, "chapter_count": 0, "draft_count": 0}
        stale_reason = "后发澄清/补遗覆盖了已映射条款，需重新确认大纲和章节。"
        chapter_rows = cur.execute(
            """
            SELECT DISTINCT bc.id, bc.chapter_code, bc.bid_outline_id
            FROM bid_chapter bc
            JOIN bid_chapter_requirement bcr ON bcr.bid_chapter_id = bc.id
            WHERE bc.project_id = %s
              AND bcr.requirement_id = ANY(%s)
            """,
            (project_id, affected_requirement_ids),
        ).fetchall()
        chapter_ids = [row["id"] for row in chapter_rows]
        chapter_codes = [row["chapter_code"] for row in chapter_rows]
        outline_ids = list({row["bid_outline_id"] for row in chapter_rows})

        if chapter_ids:
            cur.execute(
                """
                UPDATE bid_chapter
                SET is_stale = true,
                    stale_reason = %s,
                    stale_by_clarification_id = %s,
                    updated_at = now()
                WHERE id = ANY(%s)
                """,
                (stale_reason, clarification_id, chapter_ids),
            )
        if outline_ids:
            cur.execute(
                """
                UPDATE bid_outline
                SET is_stale = true,
                    stale_reason = %s,
                    stale_by_clarification_id = %s,
                    status = 'stale_pending_reconfirmation',
                    updated_at = now()
                WHERE id = ANY(%s)
                """,
                (stale_reason, clarification_id, outline_ids),
            )
        if chapter_codes:
            cur.execute(
                """
                UPDATE chapter_draft
                SET is_stale = true,
                    stale_reason = %s,
                    stale_by_clarification_id = %s,
                    updated_at = now()
                WHERE project_id = %s
                  AND chapter_code = ANY(%s)
                """,
                (stale_reason, clarification_id, project_id, chapter_codes),
            )
        return {
            "outline_count": len(outline_ids),
            "chapter_count": len(chapter_ids),
            "draft_count": len(chapter_codes),
        }

    def _category(self, text: str) -> str:
        for category, keywords in KEYWORDS_BY_CATEGORY:
            if any(keyword in text for keyword in keywords):
                return category
        return "technical"

    def _title(self, text: str, *, index: int) -> str:
        first_sentence = re.split(r"[。.!！?\n]", text, maxsplit=1)[0]
        return first_sentence[:48] or f"澄清/补遗条款 {index}"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalise(value: str) -> str:
    return re.sub(r"[\s，。；;:：、,.()（）\[\]【】《》<>\"'“”‘’]+", "", value.lower())


def _requirement_text(row: dict[str, Any]) -> str:
    return str(row.get("requirement_text") or row.get("source_text") or row.get("title") or "")


def _topic_key(text: str) -> str | None:
    for category, keywords in KEYWORDS_BY_CATEGORY:
        if any(keyword in text for keyword in keywords):
            return category
    return None


__all__ = ["ClarificationMergeService", "CLARIFICATION_EXTRACTION_METHOD", "STALE_REVIEW_STATUS"]
