"""Celery tasks for trackable AI tender extraction."""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from tender_backend.core.config import get_settings
from tender_backend.db.pool import get_pool
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.db.repositories.tender_ai_extraction_repo import TenderAiExtractionRepository
from tender_backend.db.repositories.tender_document_repository import TenderDocumentRepository
from tender_backend.services.extract_service.ai_requirements_extractor import extract_requirements_for_batch
from tender_backend.workers.celery_app import app

logger = structlog.stdlib.get_logger(__name__)

_ai_repo = TenderAiExtractionRepository()
_doc_repo = TenderDocumentRepository()
_requirement_repo = RequirementRepository()


def _run_async(coro):
    return asyncio.run(coro)


@app.task(name="tender_backend.workers.tasks_extract.run_tender_ai_extraction", bind=True)
def run_tender_ai_extraction(self, *, run_id: str) -> dict:
    """Dispatch all pending batches for an extraction run."""
    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)
    run_uuid = UUID(run_id)
    dispatched = 0
    with pool.connection() as conn:
        run = _ai_repo.get_run(conn, run_id=run_uuid)
        if run is None:
            raise ValueError(f"tender ai extraction run not found: {run_id}")
        batches = _ai_repo.list_batches(conn, run_id=run_uuid, status="pending")
        for batch in batches:
            run_tender_ai_extraction_batch.delay(batch_id=str(batch["id"]))
            dispatched += 1
        _ai_repo.refresh_run_progress(conn, run_id=run_uuid)
        conn.commit()
    logger.info("tender_ai_extraction_dispatched", run_id=run_id, dispatched=dispatched)
    return {"run_id": run_id, "dispatched": dispatched}


@app.task(name="tender_backend.workers.tasks_extract.run_tender_ai_extraction_batch", bind=True)
def run_tender_ai_extraction_batch(self, *, batch_id: str) -> dict:
    """Execute one preplanned AI extraction batch and persist its status."""
    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)
    batch_uuid = UUID(batch_id)
    with pool.connection() as conn:
        batch = _ai_repo.mark_batch_running(conn, batch_id=batch_uuid)
        if batch is None:
            existing = _ai_repo.get_batch(conn, batch_id=batch_uuid)
            return {"batch_id": batch_id, "status": existing.get("status") if existing else "missing"}
        run = _ai_repo.get_run(conn, run_id=batch["run_id"])
        if run is None:
            raise ValueError(f"tender ai extraction run not found: {batch['run_id']}")
        conn.commit()

        chunk_ids = {str(value) for value in (batch.get("chunk_ids_json") or [])}
        chunks = [
            chunk for chunk in _doc_repo.list_source_chunks(
                conn, tender_document_id=batch["tender_document_id"]
            )
            if str(chunk.get("id")) in chunk_ids
        ]
        chunks.sort(key=lambda c: (c.get("sort_order") or 0, str(c.get("id") or "")))

        persisted: list[dict] = []

        async def _persist(batch_requirements):
            if not batch_requirements:
                return
            payload = [item.to_repository_dict() for item in batch_requirements]
            rows = _requirement_repo.create_many(
                conn,
                project_id=run["project_id"],
                requirements=payload,
            )
            persisted.extend(rows)

        try:
            summary = _run_async(
                extract_requirements_for_batch(
                    chunks,
                    conn=conn,
                    source_file=batch["source_file"],
                    response_format=batch.get("response_format") or "json_object",
                    on_batch_persisted=_persist,
                )
            )
            usage = summary.batches[0] if summary.batches else None
            if usage is not None and usage.failed:
                _ai_repo.mark_batch_failed(
                    conn,
                    batch_id=batch_uuid,
                    error_type=usage.error_type or "AiExtractionError",
                    error_message=usage.error_type or "AI extraction batch failed",
                    retryable=int(batch.get("retry_count") or 0) + 1 < int(batch.get("max_retries") or 0),
                )
            else:
                _ai_repo.mark_batch_succeeded(
                    conn,
                    batch_id=batch_uuid,
                    input_tokens=summary.total_input_tokens,
                    output_tokens=summary.total_output_tokens,
                    latency_ms=usage.latency_ms if usage else 0,
                    extracted_requirements=len(persisted),
                    dropped_invalid=usage.dropped_invalid if usage else 0,
                    metadata_json={"model": usage.resolved_model if usage else None},
                )
        except Exception as exc:
            logger.exception("tender_ai_extraction_batch_failed", batch_id=batch_id)
            _ai_repo.mark_batch_failed(
                conn,
                batch_id=batch_uuid,
                error_type=type(exc).__name__,
                error_message=str(exc),
                retryable=int(batch.get("retry_count") or 0) + 1 < int(batch.get("max_retries") or 0),
            )
        run = _ai_repo.refresh_run_progress(conn, run_id=batch["run_id"])
        conn.commit()
    return {"batch_id": batch_id, "run_status": run.get("status") if run else None}


@app.task(name="tender_backend.workers.tasks_extract.retry_failed_tender_ai_extraction_batches", bind=True)
def retry_failed_tender_ai_extraction_batches(self, *, run_id: str) -> dict:
    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)
    run_uuid = UUID(run_id)
    with pool.connection() as conn:
        reset_count = _ai_repo.reset_failed_batches(conn, run_id=run_uuid)
        conn.commit()
    if reset_count:
        run_tender_ai_extraction.delay(run_id=run_id)
    return {"run_id": run_id, "reset_batches": reset_count}
