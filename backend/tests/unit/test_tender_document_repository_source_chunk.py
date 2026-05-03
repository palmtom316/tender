from __future__ import annotations

from uuid import uuid4

from tender_backend.db.repositories.tender_document_repository import TenderDocumentRepository


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self.query = query
        self.params = params
        return self

    def fetchone(self):
        return self.row


class _Conn:
    def __init__(self, row):
        self.cursor_obj = _Cursor(row)

    def cursor(self, row_factory=None):
        return self.cursor_obj


def test_get_source_chunk_queries_by_id() -> None:
    chunk_id = uuid4()
    row = {"id": chunk_id, "text": "原文"}
    conn = _Conn(row)

    result = TenderDocumentRepository().get_source_chunk(conn, source_chunk_id=chunk_id)

    assert result == row
    assert "FROM source_chunk WHERE id = %s" in conn.cursor_obj.query
    assert conn.cursor_obj.params == (chunk_id,)
