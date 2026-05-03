from __future__ import annotations

from uuid import uuid4

from tender_backend.db.repositories.scoring_repo import ScoringRepository


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
        self._row = {"dimension": params[2], "source_chunk_id": params[7], "extraction_method": params[11]}
        return self

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self):
        self.queries = []
        self.committed = False

    def cursor(self, row_factory=None):
        return _Cursor(self)

    def commit(self):
        self.committed = True


def test_create_many_persists_source_chunk_fields() -> None:
    conn = _Conn()
    source_chunk_id = uuid4()

    rows = ScoringRepository().create_many(
        conn,
        project_id=uuid4(),
        criteria=[
            {
                "dimension": "施工组织",
                "max_score": 20,
                "scoring_method": "按方案评分",
                "source_chunk_id": source_chunk_id,
                "source_file": "附件7.xlsx",
                "source_locator": "sheet:技术",
                "sub_items_json": [{"name": "完整性", "score": 5}],
                "extraction_method": "rule",
            }
        ],
    )

    assert rows[0]["source_chunk_id"] == source_chunk_id
    assert rows[0]["extraction_method"] == "rule"
    assert conn.committed is True
    assert "source_chunk_id" in conn.queries[0][0]
