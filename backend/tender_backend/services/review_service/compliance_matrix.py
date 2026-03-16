"""Compliance matrix — maps requirements to chapters and tracks coverage status."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

import structlog

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ComplianceEntry:
    requirement_id: str
    requirement_title: str
    category: str
    chapter_code: str | None
    coverage: str  # covered | partial | uncovered


def build_compliance_matrix(
    conn: Connection,
    *,
    project_id: UUID,
) -> list[ComplianceEntry]:
    """Build the compliance matrix by matching requirements to chapter drafts."""
    with conn.cursor(row_factory=dict_row) as cur:
        requirements = cur.execute(
            "SELECT id, title, category, source_text FROM project_requirement WHERE project_id = %s ORDER BY category, created_at",
            (project_id,),
        ).fetchall()

        drafts = cur.execute(
            "SELECT chapter_code, content_md FROM chapter_draft WHERE project_id = %s",
            (project_id,),
        ).fetchall()

    all_content = {d["chapter_code"]: d["content_md"] for d in drafts}
    entries: list[ComplianceEntry] = []

    for req in requirements:
        title = req["title"]
        matched_chapter = None
        coverage = "uncovered"

        for code, content in all_content.items():
            if title in content:
                matched_chapter = code
                coverage = "covered"
                break
            # Partial match: check if any keyword (>3 chars) appears
            keywords = [w for w in title.split() if len(w) > 3]
            if keywords and any(kw in content for kw in keywords):
                matched_chapter = code
                coverage = "partial"

        entries.append(ComplianceEntry(
            requirement_id=str(req["id"]),
            requirement_title=title,
            category=req["category"],
            chapter_code=matched_chapter,
            coverage=coverage,
        ))

    covered = sum(1 for e in entries if e.coverage == "covered")
    partial = sum(1 for e in entries if e.coverage == "partial")
    uncovered = sum(1 for e in entries if e.coverage == "uncovered")
    logger.info(
        "compliance_matrix_built",
        total=len(entries),
        covered=covered,
        partial=partial,
        uncovered=uncovered,
    )
    return entries
