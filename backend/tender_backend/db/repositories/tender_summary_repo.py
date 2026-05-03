"""Repository for tender_summary table."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class TenderSummaryRepository:
    def upsert(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        tender_document_id: UUID | None,
        summary: dict[str, Any],
        raw_facts_json: dict[str, Any] | None = None,
        source_chunk_ids: list[str] | None = None,
        extracted_model: str | None = None,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO tender_summary (
                  project_id, tender_document_id, project_name, tenderer, tender_agency,
                  project_location, construction_period, quality_requirement,
                  control_price, bid_bond, bid_open_time, bid_deadline,
                  raw_facts_json, source_chunk_ids_json, extracted_model
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (project_id) DO UPDATE SET
                  tender_document_id = EXCLUDED.tender_document_id,
                  project_name = EXCLUDED.project_name,
                  tenderer = EXCLUDED.tenderer,
                  tender_agency = EXCLUDED.tender_agency,
                  project_location = EXCLUDED.project_location,
                  construction_period = EXCLUDED.construction_period,
                  quality_requirement = EXCLUDED.quality_requirement,
                  control_price = EXCLUDED.control_price,
                  bid_bond = EXCLUDED.bid_bond,
                  bid_open_time = EXCLUDED.bid_open_time,
                  bid_deadline = EXCLUDED.bid_deadline,
                  raw_facts_json = EXCLUDED.raw_facts_json,
                  source_chunk_ids_json = EXCLUDED.source_chunk_ids_json,
                  extracted_model = EXCLUDED.extracted_model,
                  extracted_at = now(),
                  updated_at = now()
                RETURNING *
                """,
                (
                    project_id,
                    tender_document_id,
                    summary.get("project_name"),
                    summary.get("tenderer"),
                    summary.get("tender_agency"),
                    summary.get("project_location"),
                    summary.get("construction_period"),
                    summary.get("quality_requirement"),
                    summary.get("control_price"),
                    summary.get("bid_bond"),
                    summary.get("bid_open_time"),
                    summary.get("bid_deadline"),
                    Jsonb(raw_facts_json or {}),
                    Jsonb(source_chunk_ids or []),
                    extracted_model,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to upsert tender summary")
        return dict(row)

    def get_by_project(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM tender_summary WHERE project_id = %s",
                (project_id,),
            ).fetchone()
        return dict(row) if row else None
