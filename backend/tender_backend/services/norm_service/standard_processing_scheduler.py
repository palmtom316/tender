from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import structlog

from tender_backend.core.config import get_settings
from tender_backend.db.pool import get_pool
from tender_backend.db.repositories.standard_processing_job_repository import (
    StandardProcessingJobRepository,
)
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.norm_processor import (
    ensure_standard_ocr,
    process_standard_ai,
)

logger = structlog.stdlib.get_logger(__name__)

_scheduler_lock = threading.Lock()
_scheduler: "StandardProcessingScheduler | None" = None


class StandardProcessingScheduler:
    def __init__(
        self,
        *,
        pool,
        job_repo: StandardProcessingJobRepository | Any | None = None,
        standard_repo: StandardRepository | Any | None = None,
        run_ocr: Callable[..., int] | None = None,
        run_ai: Callable[..., dict] | None = None,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        self.pool = pool
        self.job_repo = job_repo or StandardProcessingJobRepository()
        self.standard_repo = standard_repo or StandardRepository()
        self.run_ocr = run_ocr or ensure_standard_ocr
        self.run_ai = run_ai or process_standard_ai
        self.poll_interval_seconds = poll_interval_seconds
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def ensure_started(self) -> None:
        if self._threads:
            self.wake()
            return

        self._threads = [
            threading.Thread(target=self._ocr_loop, name="standard-ocr-loop", daemon=True),
            threading.Thread(target=self._ai_loop, name="standard-ai-loop", daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        self.wake()

    def wake(self) -> None:
        self._wake_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

    def run_once(self) -> None:
        self.run_ocr_once()
        self.run_ai_once()

    def run_ocr_once(self) -> bool:
        with self.pool.connection() as conn:
            job = self.job_repo.claim_next_ocr_job(conn)
            if not job:
                return False

            self.standard_repo.update_processing_status(conn, job.standard_id, "parsing")
            try:
                self.run_ocr(conn, document_id=str(job.document_id))
            except Exception as exc:
                self.job_repo.mark_ocr_failed(conn, job_id=job.id, error=str(exc))
                self.standard_repo.update_processing_status(
                    conn, job.standard_id, "failed", error_message=str(exc)
                )
                logger.exception("standard_ocr_failed", standard_id=str(job.standard_id))
            else:
                self.job_repo.mark_ocr_completed(conn, job_id=job.id)
                self.standard_repo.update_processing_status(conn, job.standard_id, "queued_ai")
            return True

    def run_ai_once(self) -> bool:
        with self.pool.connection() as conn:
            job = self.job_repo.claim_next_ai_job(conn)
            if not job:
                return False

            self.standard_repo.update_processing_status(conn, job.standard_id, "processing")
            try:
                self.run_ai(
                    conn,
                    standard_id=job.standard_id,
                    document_id=str(job.document_id),
                )
            except Exception as exc:
                self.job_repo.mark_ai_failed(conn, job_id=job.id, error=str(exc))
                self.standard_repo.update_processing_status(
                    conn, job.standard_id, "failed", error_message=str(exc)
                )
                logger.exception("standard_ai_failed", standard_id=str(job.standard_id))
            else:
                self.job_repo.mark_ai_completed(conn, job_id=job.id)
                self.standard_repo.update_processing_status(conn, job.standard_id, "completed")
            return True

    def _ocr_loop(self) -> None:
        self._run_loop(self.run_ocr_once)

    def _ai_loop(self) -> None:
        self._run_loop(self.run_ai_once)

    def _run_loop(self, tick: Callable[[], bool]) -> None:
        while not self._stop_event.is_set():
            did_work = tick()
            if did_work:
                continue
            self._wake_event.wait(self.poll_interval_seconds)
            self._wake_event.clear()


def get_standard_processing_scheduler() -> StandardProcessingScheduler:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            settings = get_settings()
            if not settings.database_url:
                raise RuntimeError("DATABASE_URL is not configured")
            _scheduler = StandardProcessingScheduler(
                pool=get_pool(database_url=settings.database_url)
            )
        return _scheduler


def ensure_standard_processing_scheduler_started() -> StandardProcessingScheduler:
    scheduler = get_standard_processing_scheduler()
    scheduler.ensure_started()
    return scheduler
