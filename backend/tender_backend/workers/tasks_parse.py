"""Async document parsing tasks (io_tasks queue)."""

from __future__ import annotations

import structlog

from tender_backend.workers.celery_app import app

logger = structlog.stdlib.get_logger(__name__)


@app.task(name="tender_backend.workers.tasks_parse.run_parse_job", bind=True)
def run_parse_job(self, *, parse_job_id: str, document_id: str) -> dict:
    """Execute a document parse job via MinerU.

    This is the Celery entry point; actual MinerU integration
    will be implemented in Task 3 (parse_service).
    """
    logger.info(
        "parse_job_started",
        parse_job_id=parse_job_id,
        document_id=document_id,
        celery_task_id=self.request.id,
    )
    # Placeholder — Task 3 will wire in MinerU client
    return {"status": "pending_implementation", "parse_job_id": parse_job_id}
