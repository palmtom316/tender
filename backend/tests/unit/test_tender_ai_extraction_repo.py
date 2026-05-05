from __future__ import annotations

from uuid import uuid4

from tender_backend.db.repositories.tender_ai_extraction_repo import TenderAiExtractionRepository


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._row = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self.conn.queries.append((query, params))
        if "INSERT INTO tender_ai_extraction_run" in query:
            self._row = {
                "id": uuid4(),
                "tender_document_id": params[1],
                "project_id": params[2],
                "status": "pending",
                "mode": params[3],
                "model_policy": params[4],
                "total_batches": 0,
                "succeeded_batches": 0,
                "failed_batches": 0,
                "skipped_batches": 0,
                "total_chunks": 0,
                "covered_chunks": 0,
                "extracted_requirements": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "error": None,
                "metadata_json": {},
            }
        elif "INSERT INTO tender_ai_extraction_batch" in query:
            self._row = {
                "id": params[0],
                "run_id": params[1],
                "source_file": params[4],
                "batch_index": params[5],
                "status": params[6],
                "chunk_count": params[8],
            }
        elif "UPDATE tender_ai_extraction_batch" in query and "error_type = %s" in query:
            self._row = {
                "id": params[-1],
                "status": "pending",
                "error_type": params[0],
                "error_message": params[1],
            }
        elif "UPDATE tender_ai_extraction_batch" in query and "chunk_count = 0" in query:
            self._row = {
                "id": params[-1],
                "status": "succeeded",
                "chunk_count": 0,
            }
        elif "UPDATE tender_ai_extraction_batch" in query and "status = 'pending'" in query:
            self.rowcount = 2
            self._row = None
        elif "SELECT count(*)::int" in query:
            self._row = (3,)
        else:
            self._row = None
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _Conn:
    def __init__(self):
        self.queries = []

    def cursor(self, row_factory=None):
        return _Cursor(self)


def test_create_run_and_batches_emit_expected_sql() -> None:
    repo = TenderAiExtractionRepository()
    conn = _Conn()
    tender_document_id = uuid4()
    project_id = uuid4()

    run = repo.create_run(conn, tender_document_id=tender_document_id, project_id=project_id)
    rows = repo.create_batches(
        conn,
        run_id=run["id"],
        tender_document_id=tender_document_id,
        batches=[
            {
                "source_file": "采购文件.docx",
                "batch_index": 0,
                "chunk_ids": [uuid4()],
                "chunk_count": 1,
                "model": "deepseek-v4-pro",
                "reasoning_effort": "max",
            }
        ],
    )

    assert run["status"] == "pending"
    assert rows[0]["source_file"] == "采购文件.docx"
    assert any("INSERT INTO tender_ai_extraction_run" in query for query, _ in conn.queries)
    assert any("INSERT INTO tender_ai_extraction_batch" in query for query, _ in conn.queries)


def test_reset_failed_batches_returns_rowcount() -> None:
    repo = TenderAiExtractionRepository()
    conn = _Conn()

    assert repo.reset_failed_batches(conn, run_id=uuid4()) == 2


def test_count_running_batches_for_provider_returns_count() -> None:
    repo = TenderAiExtractionRepository()
    conn = _Conn()

    assert repo.count_running_batches_for_provider(
        conn,
        model="deepseek-v4-pro",
        reasoning_effort="max",
    ) == 3


def test_defer_batch_marks_pending_without_incrementing_retry() -> None:
    repo = TenderAiExtractionRepository()
    conn = _Conn()
    batch_id = uuid4()

    row = repo.defer_batch(
        conn,
        batch_id=batch_id,
        error_type="ProviderConcurrencyLimit",
        error_message="requeued",
    )

    assert row["id"] == batch_id
    assert row["status"] == "pending"
    assert any("SET status = 'pending'" in query for query, _ in conn.queries)


def test_mark_batch_superseded_zeroes_chunk_count() -> None:
    repo = TenderAiExtractionRepository()
    conn = _Conn()
    batch_id = uuid4()

    row = repo.mark_batch_superseded(
        conn,
        batch_id=batch_id,
        metadata_json={"retry_strategy": "split"},
    )

    assert row["id"] == batch_id
    assert row["status"] == "succeeded"
    assert row["chunk_count"] == 0
    assert any("chunk_count = 0" in query for query, _ in conn.queries)
