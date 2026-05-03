from __future__ import annotations

from uuid import uuid4

from tender_backend.db.repositories.tender_summary_repo import TenderSummaryRepository


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self.conn.queries.append((query, params))
        if "INSERT INTO tender_summary" in query:
            self._row = {
                "project_id": params[0],
                "tender_document_id": params[1],
                "project_name": params[2],
                "raw_facts_json": {},
                "source_chunk_ids_json": [],
                "extracted_model": params[14],
            }
        elif "SELECT * FROM tender_summary" in query:
            self._row = None
        return self

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self):
        self.queries = []

    def cursor(self, row_factory=None):
        return _Cursor(self)


def test_upsert_tender_summary_uses_project_conflict_key() -> None:
    conn = _Conn()
    repo = TenderSummaryRepository()
    project_id = uuid4()

    row = repo.upsert(
        conn,
        project_id=project_id,
        tender_document_id=uuid4(),
        summary={"project_name": "测试项目"},
        extracted_model="rule",
    )

    assert row["project_id"] == project_id
    assert row["project_name"] == "测试项目"
    assert any("ON CONFLICT (project_id)" in query for query, _ in conn.queries)
