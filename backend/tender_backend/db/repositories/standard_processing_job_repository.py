from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class StandardProcessingJob:
    id: UUID
    standard_id: UUID
    document_id: UUID
    ocr_status: str
    ocr_error: str | None
    ocr_started_at: datetime | None
    ocr_finished_at: datetime | None
    ocr_attempts: int
    ai_status: str
    ai_error: str | None
    ai_started_at: datetime | None
    ai_finished_at: datetime | None
    ai_attempts: int
    created_at: datetime
    updated_at: datetime


class StandardProcessingJobRepository:
    def create(
        self,
        conn: Connection,
        *,
        standard_id: UUID,
        document_id: UUID,
    ) -> StandardProcessingJob:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO standard_processing_job (
                  id, standard_id, document_id
                ) VALUES (%s, %s, %s)
                RETURNING *
                """,
                (uuid4(), standard_id, document_id),
            ).fetchone()
        conn.commit()
        assert row is not None
        return self._row_to_job(row)

    def get_by_standard_id(
        self,
        conn: Connection,
        *,
        standard_id: UUID,
    ) -> StandardProcessingJob | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM standard_processing_job WHERE standard_id = %s",
                (standard_id,),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def claim_next_ocr_job(self, conn: Connection) -> StandardProcessingJob | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE standard_processing_job
                SET
                  ocr_status = 'running',
                  ocr_attempts = ocr_attempts + 1,
                  ocr_started_at = COALESCE(ocr_started_at, now()),
                  updated_at = now()
                WHERE id = (
                  SELECT id
                  FROM standard_processing_job
                  WHERE ocr_status = 'queued'
                  ORDER BY created_at
                  LIMIT 1
                  FOR UPDATE SKIP LOCKED
                )
                RETURNING *
                """
            ).fetchone()
        conn.commit()
        return self._row_to_job(row) if row else None

    def claim_next_ai_job(self, conn: Connection) -> StandardProcessingJob | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE standard_processing_job
                SET
                  ai_status = 'running',
                  ai_attempts = ai_attempts + 1,
                  ai_started_at = COALESCE(ai_started_at, now()),
                  updated_at = now()
                WHERE id = (
                  SELECT id
                  FROM standard_processing_job
                  WHERE ai_status = 'queued'
                  ORDER BY created_at
                  LIMIT 1
                  FOR UPDATE SKIP LOCKED
                )
                RETURNING *
                """
            ).fetchone()
        conn.commit()
        return self._row_to_job(row) if row else None

    def mark_ocr_completed(self, conn: Connection, *, job_id: UUID) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE standard_processing_job
                SET
                  ocr_status = 'completed',
                  ocr_error = NULL,
                  ocr_finished_at = now(),
                  ai_status = 'queued',
                  ai_error = NULL,
                  updated_at = now()
                WHERE id = %s
                """,
                (job_id,),
            )
        conn.commit()

    def mark_ocr_failed(self, conn: Connection, *, job_id: UUID, error: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE standard_processing_job
                SET
                  ocr_status = 'failed',
                  ocr_error = %s,
                  ocr_finished_at = now(),
                  updated_at = now()
                WHERE id = %s
                """,
                (error, job_id),
            )
        conn.commit()

    def mark_ai_completed(self, conn: Connection, *, job_id: UUID) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE standard_processing_job
                SET
                  ai_status = 'completed',
                  ai_error = NULL,
                  ai_finished_at = now(),
                  updated_at = now()
                WHERE id = %s
                """,
                (job_id,),
            )
        conn.commit()

    def mark_ai_failed(self, conn: Connection, *, job_id: UUID, error: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE standard_processing_job
                SET
                  ai_status = 'failed',
                  ai_error = %s,
                  ai_finished_at = now(),
                  updated_at = now()
                WHERE id = %s
                """,
                (error, job_id),
            )
        conn.commit()

    def retry(self, conn: Connection, *, standard_id: UUID) -> StandardProcessingJob:
        current = self.get_by_standard_id(conn, standard_id=standard_id)
        if current is None:
            raise ValueError(f"Standard processing job not found: {standard_id}")

        if current.ocr_status == "failed":
            sql = """
                UPDATE standard_processing_job
                SET
                  ocr_status = 'queued',
                  ocr_error = NULL,
                  ocr_started_at = NULL,
                  ocr_finished_at = NULL,
                  ai_status = 'blocked',
                  ai_error = NULL,
                  ai_started_at = NULL,
                  ai_finished_at = NULL,
                  updated_at = now()
                WHERE standard_id = %s
                RETURNING *
            """
        elif current.ai_status == "failed" and current.ocr_status == "completed":
            sql = """
                UPDATE standard_processing_job
                SET
                  ai_status = 'queued',
                  ai_error = NULL,
                  ai_started_at = NULL,
                  ai_finished_at = NULL,
                  updated_at = now()
                WHERE standard_id = %s
                RETURNING *
            """
        else:
            raise ValueError(f"Standard processing job is not retryable: {standard_id}")

        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(sql, (standard_id,)).fetchone()
        conn.commit()
        assert row is not None
        return self._row_to_job(row)

    @staticmethod
    def _row_to_job(row: dict) -> StandardProcessingJob:
        return StandardProcessingJob(
            id=row["id"],
            standard_id=row["standard_id"],
            document_id=row["document_id"],
            ocr_status=row["ocr_status"],
            ocr_error=row.get("ocr_error"),
            ocr_started_at=row.get("ocr_started_at"),
            ocr_finished_at=row.get("ocr_finished_at"),
            ocr_attempts=row["ocr_attempts"],
            ai_status=row["ai_status"],
            ai_error=row.get("ai_error"),
            ai_started_at=row.get("ai_started_at"),
            ai_finished_at=row.get("ai_finished_at"),
            ai_attempts=row["ai_attempts"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
