"""Repository for tender AI extraction run and batch tracking."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


_TERMINAL_STATUSES = {"succeeded", "failed", "skipped", "needs_review"}


class TenderAiExtractionRepository:
    def create_run(
        self,
        conn: Connection,
        *,
        tender_document_id: UUID,
        project_id: UUID,
        mode: str = "requirements",
        model_policy: str = "v4_flash_then_pro",
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO tender_ai_extraction_run (
                  id, tender_document_id, project_id, status, mode, model_policy, metadata_json
                )
                VALUES (%s, %s, %s, 'pending', %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    tender_document_id,
                    project_id,
                    mode,
                    model_policy,
                    Jsonb(metadata_json or {}),
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to create tender ai extraction run")
        return dict(row)

    def get_run(self, conn: Connection, *, run_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM tender_ai_extraction_run WHERE id = %s",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_latest_active_run_for_document(
        self,
        conn: Connection,
        *,
        tender_document_id: UUID,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT *
                FROM tender_ai_extraction_run
                WHERE tender_document_id = %s
                  AND status IN ('pending', 'running', 'partial')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (tender_document_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_batches(
        self,
        conn: Connection,
        *,
        run_id: UUID,
        tender_document_id: UUID,
        batches: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with conn.cursor(row_factory=dict_row) as cur:
            for batch in batches:
                row = cur.execute(
                    """
                    INSERT INTO tender_ai_extraction_batch (
                      id, run_id, tender_document_id, tender_document_file_id, source_file,
                      batch_index, status, chunk_ids_json, chunk_count, input_char_count,
                      estimated_input_tokens, model, reasoning_effort, response_format,
                      max_retries, skip_reason, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, source_file, batch_index) DO UPDATE SET
                      status = EXCLUDED.status,
                      chunk_ids_json = EXCLUDED.chunk_ids_json,
                      chunk_count = EXCLUDED.chunk_count,
                      input_char_count = EXCLUDED.input_char_count,
                      estimated_input_tokens = EXCLUDED.estimated_input_tokens,
                      model = EXCLUDED.model,
                      reasoning_effort = EXCLUDED.reasoning_effort,
                      response_format = EXCLUDED.response_format,
                      max_retries = EXCLUDED.max_retries,
                      skip_reason = EXCLUDED.skip_reason,
                      metadata_json = EXCLUDED.metadata_json,
                      updated_at = now()
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        run_id,
                        tender_document_id,
                        batch.get("tender_document_file_id"),
                        batch["source_file"],
                        batch["batch_index"],
                        batch.get("status", "pending"),
                        Jsonb([str(chunk_id) for chunk_id in batch.get("chunk_ids", [])]),
                        batch.get("chunk_count", 0),
                        batch.get("input_char_count", 0),
                        batch.get("estimated_input_tokens", 0),
                        batch.get("model", "deepseek-v4-flash"),
                        batch.get("reasoning_effort"),
                        batch.get("response_format", "json_object"),
                        batch.get("max_retries", 2),
                        batch.get("skip_reason"),
                        Jsonb(batch.get("metadata_json") or {}),
                    ),
                ).fetchone()
                if row is not None:
                    rows.append(dict(row))
        return rows

    def refresh_run_progress(self, conn: Connection, *, run_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                WITH aggregate AS (
                  SELECT
                    count(*)::int AS total_batches,
                    count(*) FILTER (WHERE status = 'succeeded')::int AS succeeded_batches,
                    count(*) FILTER (WHERE status = 'failed')::int AS failed_batches,
                    count(*) FILTER (WHERE status = 'skipped')::int AS skipped_batches,
                    COALESCE(sum(chunk_count), 0)::int AS total_chunks,
                    COALESCE(sum(chunk_count) FILTER (WHERE status = 'succeeded'), 0)::int AS covered_chunks,
                    COALESCE(sum(extracted_requirements), 0)::int AS extracted_requirements,
                    COALESCE(sum(input_tokens), 0)::int AS total_input_tokens,
                    COALESCE(sum(output_tokens), 0)::int AS total_output_tokens,
                    bool_or(status = 'running') AS has_running,
                    bool_or(status = 'pending') AS has_pending,
                    bool_or(status = 'failed') AS has_failed,
                    bool_or(status = 'needs_review') AS has_needs_review
                  FROM tender_ai_extraction_batch
                  WHERE run_id = %s
                )
                UPDATE tender_ai_extraction_run r
                SET total_batches = aggregate.total_batches,
                    succeeded_batches = aggregate.succeeded_batches,
                    failed_batches = aggregate.failed_batches,
                    skipped_batches = aggregate.skipped_batches,
                    total_chunks = aggregate.total_chunks,
                    covered_chunks = aggregate.covered_chunks,
                    extracted_requirements = aggregate.extracted_requirements,
                    total_input_tokens = aggregate.total_input_tokens,
                    total_output_tokens = aggregate.total_output_tokens,
                    status = CASE
                      WHEN aggregate.total_batches = 0 THEN 'failed'
                      WHEN aggregate.has_failed OR aggregate.has_needs_review THEN 'partial'
                      WHEN aggregate.has_running THEN 'running'
                      WHEN aggregate.has_pending THEN 'pending'
                      ELSE 'completed'
                    END,
                    started_at = CASE
                      WHEN r.started_at IS NULL AND (aggregate.has_running OR aggregate.succeeded_batches > 0)
                      THEN now()
                      ELSE r.started_at
                    END,
                    finished_at = CASE
                      WHEN aggregate.total_batches > 0
                       AND NOT aggregate.has_running
                       AND NOT aggregate.has_pending
                      THEN now()
                      ELSE NULL
                    END,
                    updated_at = now()
                FROM aggregate
                WHERE r.id = %s
                RETURNING r.*
                """,
                (run_id, run_id),
            ).fetchone()
        return dict(row) if row else None

    def list_batches(
        self,
        conn: Connection,
        *,
        run_id: UUID,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM tender_ai_extraction_batch WHERE run_id = %s"
        params: list[Any] = [run_id]
        if status:
            query += " AND status = %s"
            params.append(status)
        query += " ORDER BY source_file, batch_index"
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def aggregate_file_coverage(self, conn: Connection, *, run_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    source_file,
                    COUNT(*) AS batches,
                    COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                    COUNT(*) FILTER (WHERE status = 'needs_review') AS needs_review,
                    COUNT(*) FILTER (WHERE status = 'skipped') AS skipped,
                    COALESCE(SUM(chunk_count), 0) AS chunks,
                    COALESCE(SUM(extracted_requirements), 0) AS extracted_requirements,
                    MAX(skip_reason) FILTER (WHERE status = 'skipped') AS skip_reason
                FROM tender_ai_extraction_batch
                WHERE run_id = %s
                GROUP BY source_file
                ORDER BY source_file
                """,
                (run_id,),
            )
            columns = [column.name for column in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def get_batch(self, conn: Connection, *, batch_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM tender_ai_extraction_batch WHERE id = %s",
                (batch_id,),
            ).fetchone()
        return dict(row) if row else None

    def mark_batch_running(self, conn: Connection, *, batch_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_ai_extraction_batch
                SET status = 'running', started_at = COALESCE(started_at, now()),
                    error_type = NULL, error_message = NULL, updated_at = now()
                WHERE id = %s AND status IN ('pending', 'failed', 'needs_review')
                RETURNING *
                """,
                (batch_id,),
            ).fetchone()
        return dict(row) if row else None

    def count_running_batches_for_provider(
        self,
        conn: Connection,
        *,
        model: str,
        reasoning_effort: str | None = None,
        thinking_enabled: bool | None = None,
        quality_policy: str | None = None,
    ) -> int:
        thinking_text = None if thinking_enabled is None else ("true" if thinking_enabled else "false")
        filter_thinking = thinking_text is not None
        filter_quality = quality_policy is not None
        with conn.cursor() as cur:
            row = cur.execute(
                """
                SELECT count(*)::int
                FROM tender_ai_extraction_batch
                WHERE status = 'running'
                  AND model = %s
                  AND reasoning_effort IS NOT DISTINCT FROM %s
                  AND (
                    NOT %s OR COALESCE(metadata_json->>'thinking_enabled', '') = %s
                  )
                  AND (
                    NOT %s OR COALESCE(metadata_json->>'quality_policy', '') = %s
                  )
                """,
                (
                    model,
                    reasoning_effort,
                    filter_thinking,
                    thinking_text,
                    filter_quality,
                    quality_policy,
                ),
            ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def create_review_batch(
        self,
        conn: Connection,
        *,
        source_batch: dict[str, Any],
        batch_index: int,
        model: str,
        reasoning_effort: str | None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = self.create_batches(
            conn,
            run_id=source_batch["run_id"],
            tender_document_id=source_batch["tender_document_id"],
            batches=[
                {
                    "tender_document_file_id": source_batch.get("tender_document_file_id"),
                    "source_file": source_batch["source_file"],
                    "batch_index": batch_index,
                    "chunk_ids": source_batch.get("chunk_ids_json") or [],
                    "status": "pending",
                    "chunk_count": 0,
                    "input_char_count": source_batch.get("input_char_count", 0),
                    "estimated_input_tokens": source_batch.get("estimated_input_tokens", 0),
                    "model": model,
                    "reasoning_effort": reasoning_effort,
                    "response_format": source_batch.get("response_format", "json_object"),
                    "max_retries": 1,
                    "metadata_json": metadata_json or {},
                }
            ],
        )
        return rows[0] if rows else None

    def create_retry_batches(
        self,
        conn: Connection,
        *,
        source_batch: dict[str, Any],
        retry_batches: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self.create_batches(
            conn,
            run_id=source_batch["run_id"],
            tender_document_id=source_batch["tender_document_id"],
            batches=retry_batches,
        )

    def mark_batch_succeeded(
        self,
        conn: Connection,
        *,
        batch_id: UUID,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        extracted_requirements: int,
        dropped_invalid: int,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_ai_extraction_batch
                SET status = 'succeeded', input_tokens = %s, output_tokens = %s,
                    latency_ms = %s, extracted_requirements = %s, dropped_invalid = %s,
                    error_type = NULL, error_message = NULL,
                    metadata_json = COALESCE(%s, metadata_json),
                    finished_at = now(), updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    extracted_requirements,
                    dropped_invalid,
                    Jsonb(metadata_json) if metadata_json is not None else None,
                    batch_id,
                ),
            ).fetchone()
        return dict(row) if row else None

    def defer_batch(
        self,
        conn: Connection,
        *,
        batch_id: UUID,
        error_type: str,
        error_message: str,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_ai_extraction_batch
                SET status = 'pending',
                    error_type = %s,
                    error_message = %s,
                    started_at = NULL,
                    finished_at = NULL,
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (error_type, error_message[:2000], batch_id),
            ).fetchone()
        return dict(row) if row else None

    def mark_batch_superseded(
        self,
        conn: Connection,
        *,
        batch_id: UUID,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_ai_extraction_batch
                SET status = 'succeeded',
                    chunk_count = 0,
                    input_tokens = 0,
                    output_tokens = 0,
                    latency_ms = 0,
                    extracted_requirements = 0,
                    dropped_invalid = 0,
                    error_type = NULL,
                    error_message = NULL,
                    metadata_json = COALESCE(%s, metadata_json),
                    finished_at = now(),
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (Jsonb(metadata_json) if metadata_json is not None else None, batch_id),
            ).fetchone()
        return dict(row) if row else None

    def mark_batch_failed(
        self,
        conn: Connection,
        *,
        batch_id: UUID,
        error_type: str,
        error_message: str,
        retryable: bool = True,
    ) -> dict[str, Any] | None:
        status = "failed" if retryable else "needs_review"
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_ai_extraction_batch
                SET status = %s, retry_count = retry_count + 1,
                    error_type = %s, error_message = %s,
                    finished_at = now(), updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (status, error_type, error_message[:2000], batch_id),
            ).fetchone()
        return dict(row) if row else None

    def reset_failed_batches(self, conn: Connection, *, run_id: UUID) -> int:
        with conn.cursor() as cur:
            result = cur.execute(
                """
                UPDATE tender_ai_extraction_batch
                SET status = 'pending', error_type = NULL, error_message = NULL,
                    started_at = NULL, finished_at = NULL, updated_at = now()
                WHERE run_id = %s
                  AND status IN ('failed', 'needs_review')
                  AND retry_count < max_retries
                """,
                (run_id,),
            )
        return int(result.rowcount or 0)

    def terminal_statuses(self) -> set[str]:
        return set(_TERMINAL_STATUSES)
