"""Repository for task_trace table."""

from __future__ import annotations

from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


class TraceRepository:
    def create(
        self,
        conn: Connection,
        *,
        task_type: str,
        model: str | None = None,
        provider: str | None = None,
        prompt_version: str | None = None,
        workflow_run_id: UUID | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: float = 0.0,
        latency_ms: int = 0,
        status: str = "completed",
        error: str | None = None,
    ) -> dict:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO task_trace
                    (id, workflow_run_id, task_type, model, provider,
                     prompt_version, input_tokens, output_tokens,
                     estimated_cost, latency_ms, status, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(), workflow_run_id, task_type, model, provider,
                    prompt_version, input_tokens, output_tokens,
                    estimated_cost, latency_ms, status, error,
                ),
            ).fetchone()
        conn.commit()
        return row  # type: ignore[return-value]

    def list_by_workflow(self, conn: Connection, *, workflow_run_id: UUID) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT * FROM task_trace WHERE workflow_run_id = %s ORDER BY created_at",
                (workflow_run_id,),
            ).fetchall()

    def list_by_prompt_version(
        self, conn: Connection, *, prompt_version: str
    ) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT * FROM task_trace WHERE prompt_version = %s ORDER BY created_at",
                (prompt_version,),
            ).fetchall()
