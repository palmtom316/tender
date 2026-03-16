"""Repository for workflow_run and workflow_step_log persistence."""

from __future__ import annotations

import json
from typing import Any

from psycopg import Connection

from tender_backend.workflows.states import StepState, WorkflowState


class WorkflowRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def create_run(
        self,
        *,
        run_id: str,
        workflow_name: str,
        project_id: str,
        trace_id: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO workflow_run (id, workflow_name, project_id, state, trace_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (run_id, workflow_name, project_id, WorkflowState.PENDING, trace_id),
        )

    async def get_run(self, run_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM workflow_run WHERE id = %s", (run_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Workflow run {run_id} not found")
        cols = [d.name for d in self._conn.execute(
            "SELECT * FROM workflow_run WHERE id = %s", (run_id,)
        ).description]
        return dict(zip(cols, row))

    async def update_run_state(
        self,
        run_id: str,
        state: WorkflowState,
        *,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE workflow_run
            SET state = %s, error_message = COALESCE(%s, error_message),
                updated_at = now()
            WHERE id = %s
            """,
            (state, error, run_id),
        )

    async def update_run_current_step(self, run_id: str, step_name: str) -> None:
        self._conn.execute(
            "UPDATE workflow_run SET current_step = %s, updated_at = now() WHERE id = %s",
            (step_name, run_id),
        )

    async def save_context(self, run_id: str, data: dict) -> None:
        self._conn.execute(
            "UPDATE workflow_run SET context_json = %s, updated_at = now() WHERE id = %s",
            (json.dumps(data), run_id),
        )

    async def create_step_log(
        self,
        *,
        step_log_id: str,
        workflow_run_id: str,
        step_name: str,
        state: StepState,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO workflow_step_log (id, workflow_run_id, step_name, state)
            VALUES (%s, %s, %s, %s)
            """,
            (step_log_id, workflow_run_id, step_name, state),
        )

    async def finish_step_log(
        self, step_log_id: str, state: StepState, message: str = ""
    ) -> None:
        self._conn.execute(
            """
            UPDATE workflow_step_log
            SET state = %s, message = %s, finished_at = now()
            WHERE id = %s
            """,
            (state, message, step_log_id),
        )
