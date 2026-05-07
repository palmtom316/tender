from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class PostBidReviewRepository:
    def upsert(self, conn: Connection, *, project_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
        existing = self.get(conn, project_id=project_id)
        allowed = {
            "bid_result", "ranking", "score", "price_metadata", "competitor_notes", "win_loss_reasons",
            "reusable_lessons", "opening_record_json", "clarification_json", "notice_json", "contract_status",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        json_keys = {"price_metadata", "opening_record_json", "clarification_json", "notice_json"}
        if existing is None:
            columns = ["id", "project_id", *values.keys()]
            params = [uuid4(), project_id, *[Jsonb(value) if key in json_keys else value for key, value in values.items()]]
            placeholders = ", ".join(["%s"] * len(columns))
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute(
                    f"INSERT INTO post_bid_review ({', '.join(columns)}) VALUES ({placeholders}) RETURNING *",
                    params,
                ).fetchone()
        else:
            sets = [f"{key} = %s" for key in values]
            params = [Jsonb(value) if key in json_keys else value for key, value in values.items()]
            params.append(project_id)
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute(
                    f"UPDATE post_bid_review SET {', '.join(sets)}, updated_at = now() WHERE project_id = %s RETURNING *",
                    params,
                ).fetchone()
        conn.commit()
        return dict(row) if row else {}

    def get(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute("SELECT * FROM post_bid_review WHERE project_id = %s ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone()
        return dict(row) if row else None


__all__ = ["PostBidReviewRepository"]
