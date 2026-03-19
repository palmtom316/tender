from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from tender_backend.services.norm_service.standard_processing_scheduler import (
    StandardProcessingScheduler,
)


class _FakePool:
    @contextmanager
    def connection(self):
        yield object()


def _job(*, ocr_status: str, ai_status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        standard_id=uuid4(),
        document_id=uuid4(),
        ocr_status=ocr_status,
        ai_status=ai_status,
    )


def test_run_ocr_once_claims_only_one_queued_job() -> None:
    first = _job(ocr_status="queued", ai_status="blocked")
    jobs = [first, _job(ocr_status="queued", ai_status="blocked")]
    captured: dict[str, object] = {"ocr_calls": []}

    class _JobRepo:
        def claim_next_ocr_job(self, conn):
            return jobs.pop(0) if jobs else None

        def mark_ocr_completed(self, conn, *, job_id):
            captured["completed_job_id"] = job_id

    class _StandardRepo:
        def update_processing_status(self, conn, standard_id, status, error_message=None):
            captured.setdefault("statuses", []).append((standard_id, status, error_message))

    scheduler = StandardProcessingScheduler(
        pool=_FakePool(),
        job_repo=_JobRepo(),
        standard_repo=_StandardRepo(),
        run_ocr=lambda conn, *, document_id: captured["ocr_calls"].append(document_id),
        run_ai=lambda conn, *, standard_id, document_id: None,
    )

    processed = scheduler.run_ocr_once()

    assert processed is True
    assert captured["ocr_calls"] == [str(first.document_id)]
    assert captured["completed_job_id"] == first.id
    assert len(captured["statuses"]) == 2


def test_run_ai_once_claims_only_one_ready_job() -> None:
    first = _job(ocr_status="completed", ai_status="queued")
    jobs = [first, _job(ocr_status="completed", ai_status="queued")]
    captured: dict[str, object] = {"ai_calls": []}

    class _JobRepo:
        def claim_next_ai_job(self, conn):
            return jobs.pop(0) if jobs else None

        def mark_ai_completed(self, conn, *, job_id):
            captured["completed_job_id"] = job_id

    class _StandardRepo:
        def update_processing_status(self, conn, standard_id, status, error_message=None):
            captured.setdefault("statuses", []).append((standard_id, status, error_message))

    scheduler = StandardProcessingScheduler(
        pool=_FakePool(),
        job_repo=_JobRepo(),
        standard_repo=_StandardRepo(),
        run_ocr=lambda conn, *, document_id: None,
        run_ai=lambda conn, *, standard_id, document_id: captured["ai_calls"].append((standard_id, document_id)),
    )

    processed = scheduler.run_ai_once()

    assert processed is True
    assert captured["ai_calls"] == [(first.standard_id, str(first.document_id))]
    assert captured["completed_job_id"] == first.id
    assert len(captured["statuses"]) == 2


def test_run_once_processes_one_ocr_and_one_ai_in_same_tick() -> None:
    ocr_job = _job(ocr_status="queued", ai_status="blocked")
    ai_job = _job(ocr_status="completed", ai_status="queued")
    captured: dict[str, list] = {"ocr_calls": [], "ai_calls": []}

    class _JobRepo:
        def __init__(self) -> None:
            self.ocr_claimed = False
            self.ai_claimed = False

        def claim_next_ocr_job(self, conn):
            if self.ocr_claimed:
                return None
            self.ocr_claimed = True
            return ocr_job

        def claim_next_ai_job(self, conn):
            if self.ai_claimed:
                return None
            self.ai_claimed = True
            return ai_job

        def mark_ocr_completed(self, conn, *, job_id):
            captured.setdefault("ocr_completed", []).append(job_id)

        def mark_ai_completed(self, conn, *, job_id):
            captured.setdefault("ai_completed", []).append(job_id)

    class _StandardRepo:
        def update_processing_status(self, conn, standard_id, status, error_message=None):
            captured.setdefault("statuses", []).append((standard_id, status))

    scheduler = StandardProcessingScheduler(
        pool=_FakePool(),
        job_repo=_JobRepo(),
        standard_repo=_StandardRepo(),
        run_ocr=lambda conn, *, document_id: captured["ocr_calls"].append(document_id),
        run_ai=lambda conn, *, standard_id, document_id: captured["ai_calls"].append((standard_id, document_id)),
    )

    scheduler.run_once()

    assert captured["ocr_calls"] == [str(ocr_job.document_id)]
    assert captured["ai_calls"] == [(ai_job.standard_id, str(ai_job.document_id))]
    assert captured["ocr_completed"] == [ocr_job.id]
    assert captured["ai_completed"] == [ai_job.id]


def test_failed_ocr_job_does_not_block_next_queued_job() -> None:
    failed = _job(ocr_status="queued", ai_status="blocked")
    second = _job(ocr_status="queued", ai_status="blocked")
    captured: dict[str, list] = {"ocr_calls": []}

    class _JobRepo:
        def __init__(self) -> None:
            self.jobs = [failed, second]

        def claim_next_ocr_job(self, conn):
            return self.jobs.pop(0) if self.jobs else None

        def mark_ocr_completed(self, conn, *, job_id):
            captured.setdefault("completed", []).append(job_id)

        def mark_ocr_failed(self, conn, *, job_id, error):
            captured.setdefault("failed", []).append((job_id, error))

    class _StandardRepo:
        def update_processing_status(self, conn, standard_id, status, error_message=None):
            captured.setdefault("statuses", []).append((standard_id, status, error_message))

    def _run_ocr(conn, *, document_id):
        captured["ocr_calls"].append(document_id)
        if document_id == str(failed.document_id):
            raise RuntimeError("ocr blew up")

    scheduler = StandardProcessingScheduler(
        pool=_FakePool(),
        job_repo=_JobRepo(),
        standard_repo=_StandardRepo(),
        run_ocr=_run_ocr,
        run_ai=lambda conn, *, standard_id, document_id: None,
    )

    assert scheduler.run_ocr_once() is True
    assert scheduler.run_ocr_once() is True
    assert captured["ocr_calls"] == [str(failed.document_id), str(second.document_id)]
    assert captured["failed"] == [(failed.id, "ocr blew up")]
    assert captured["completed"] == [second.id]
