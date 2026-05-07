"""Post-bid retrospective service and lightweight analytics."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.db.repositories.post_bid_review_repo import PostBidReviewRepository


class PostBidReviewService:
    def __init__(self) -> None:
        self._repo = PostBidReviewRepository()

    def get(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        return self._repo.get(conn, project_id=project_id)

    def upsert(self, conn: Connection, *, project_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
        return self._repo.upsert(conn, project_id=project_id, fields=fields)

    def analytics(self, conn: Connection) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT p.business_line, p.voltage_level, p.selected_template_package_id,
                       r.bid_result, COUNT(*) AS count
                FROM post_bid_review r
                JOIN project p ON p.id = r.project_id
                GROUP BY p.business_line, p.voltage_level, p.selected_template_package_id, r.bid_result
                ORDER BY p.business_line NULLS LAST, r.bid_result
                """
            ).fetchall()
        buckets: dict[str, dict[str, int]] = {}
        for row in rows:
            key = row.get("business_line") or "unknown"
            buckets.setdefault(key, {})
            buckets[key][row["bid_result"]] = int(row["count"])
        return {"by_business_line": buckets, "rows": [dict(row) for row in rows]}


__all__ = ["PostBidReviewService"]
