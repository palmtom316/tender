from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID

from tender_backend.tools import reindex_standard_clauses


def test_build_clause_index_docs_maps_standard_and_clause_fields() -> None:
    standard = {
        "id": UUID("11111111-1111-1111-1111-111111111111"),
        "standard_code": "GB 123",
        "standard_name": "安装工程施工规范",
        "specialty": "安装",
    }
    clauses = [{
        "id": UUID("22222222-2222-2222-2222-222222222222"),
        "clause_no": "3.1.1",
        "clause_title": "一般规定",
        "clause_text": "条文内容",
        "summary": "摘要",
        "tags": ["强制性条文"],
        "page_start": 8,
        "page_end": 9,
    }]

    docs = reindex_standard_clauses.build_clause_index_docs(standard, clauses)

    assert docs == [(
        "22222222-2222-2222-2222-222222222222",
        {
            "standard_id": "11111111-1111-1111-1111-111111111111",
            "standard_code": "GB 123",
            "standard_name": "安装工程施工规范",
            "clause_id": "22222222-2222-2222-2222-222222222222",
            "clause_no": "3.1.1",
            "clause_title": "一般规定",
            "clause_text": "条文内容",
            "summary": "摘要",
            "tags": ["强制性条文"],
            "specialty": "安装",
            "page_start": 8,
            "page_end": 9,
        },
    )]


def test_reindex_standard_clauses_calls_bulk_index(monkeypatch) -> None:
    standard = {
        "id": UUID("11111111-1111-1111-1111-111111111111"),
        "standard_code": "GB 123",
        "standard_name": "安装工程施工规范",
        "specialty": "安装",
    }
    clauses = [{
        "id": UUID("22222222-2222-2222-2222-222222222222"),
        "clause_no": "3.1.1",
        "clause_title": "一般规定",
        "clause_text": "条文内容",
        "summary": "摘要",
        "tags": ["强制性条文"],
        "page_start": 8,
        "page_end": 9,
    }]
    captured: dict[str, object] = {}

    class _FakeRepo:
        def get_standard(self, conn, standard_id):
            captured["standard_id"] = standard_id
            return standard

        def list_clauses(self, conn, *, standard_id):
            captured["list_standard_id"] = standard_id
            return clauses

    class _FakeManager:
        async def create_index(self, name: str, body: dict) -> None:
            captured["create_index"] = name
            captured["create_body"] = body

        async def bulk_index(self, index: str, docs):
            captured["index"] = index
            captured["docs"] = docs
            return len(docs)

    monkeypatch.setattr(reindex_standard_clauses, "_repo", _FakeRepo())
    monkeypatch.setattr(reindex_standard_clauses, "IndexManager", lambda: _FakeManager())

    count = asyncio.run(reindex_standard_clauses.reindex_standard_clauses(
        conn=object(),
        standard_id=UUID("11111111-1111-1111-1111-111111111111"),
    ))

    assert count == 1
    assert captured["create_index"] == "clause_index"
    assert captured["index"] == "clause_index"
    assert captured["docs"] == reindex_standard_clauses.build_clause_index_docs(standard, clauses)
