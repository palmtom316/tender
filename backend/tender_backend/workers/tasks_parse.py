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


@app.task(name="tender_backend.workers.tasks_parse.run_standard_processing", bind=True)
def run_standard_processing(self, *, standard_id: str, document_id: str) -> dict:
    """Process a standard document: extract clauses via AI and build clause tree."""
    from uuid import UUID

    from tender_backend.core.config import get_settings
    from tender_backend.db.pool import get_pool
    from tender_backend.services.norm_service.norm_processor import process_standard

    logger.info(
        "standard_processing_started",
        standard_id=standard_id,
        document_id=document_id,
        celery_task_id=self.request.id,
    )

    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)
    with pool.connection() as conn:
        result = process_standard(conn, UUID(standard_id), document_id)

    logger.info("standard_processing_finished", result=result)
    return result
