from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest


@pytest.mark.parametrize("query", ["变压器"])
def test_search_standards_drops_stale_index_hits_without_live_clause(monkeypatch, query: str) -> None:
    import tender_backend.api.standards as standards_api

    live_clause_id = str(uuid4())
    stale_clause_id = str(uuid4())
    live_standard_id = str(uuid4())
    stale_standard_id = str(uuid4())
    cleaned_clause_ids: list[str] = []

    async def fake_search_standard_clauses(
        q: str,
        *,
        specialty: str | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        assert q == query
        assert specialty is None
        assert top_k == 10
        return [
            {
                "standard_id": stale_standard_id,
                "standard_name": "已删除规范",
                "clause_id": stale_clause_id,
                "clause_no": "9.9.9",
                "summary": "脏索引命中",
                "page_start": 99,
                "page_end": 99,
                "tags": ["脏数据"],
            },
            {
                "standard_id": str(uuid4()),
                "standard_name": "旧索引里的错误标准名",
                "clause_id": live_clause_id,
                "clause_no": "4.2.1",
                "summary": "有效命中",
                "page_start": 17,
                "page_end": 18,
                "tags": ["设备"],
            },
        ]

    def fake_get_clauses_by_ids(_conn, clause_ids):
        assert [str(clause_id) for clause_id in clause_ids] == [stale_clause_id, live_clause_id]
        return {
            live_clause_id: {
                "id": live_clause_id,
                "standard_id": live_standard_id,
                "standard_name": "电气装置安装工程 电力变压器施工规范",
                "specialty": "电气",
                "clause_no": "4.2.1",
                "page_start": 17,
                "page_end": 18,
                "tags": ["设备"],
            },
        }

    def fake_get_standard(_conn, standard_id: UUID):
        if str(standard_id) == stale_standard_id:
            return {"id": stale_standard_id}
        if str(standard_id) == live_standard_id:
            return {"id": live_standard_id}
        return None

    monkeypatch.setattr(standards_api, "search_standard_clauses", fake_search_standard_clauses, raising=False)
    monkeypatch.setattr(standards_api._repo, "get_clauses_by_ids", fake_get_clauses_by_ids, raising=False)
    monkeypatch.setattr(standards_api._repo, "get_standard", fake_get_standard, raising=False)
    async def fake_delete_stale_clause_hits_from_index(clause_ids: list[str]) -> None:
        cleaned_clause_ids.extend(clause_ids)

    monkeypatch.setattr(
        standards_api,
        "delete_stale_clause_hits_from_index",
        fake_delete_stale_clause_hits_from_index,
        raising=False,
    )

    payload = asyncio.run(
        standards_api.search_standards(q=query, specialty=None, top_k=10, conn=object()),
    )

    assert cleaned_clause_ids == [stale_clause_id]
    assert payload == [
        {
            "standard_id": live_standard_id,
            "standard_name": "电气装置安装工程 电力变压器施工规范",
            "specialty": "电气",
            "clause_id": live_clause_id,
            "clause_no": "4.2.1",
            "tags": ["设备"],
            "summary": "有效命中",
            "page_start": 17,
            "page_end": 18,
        }
    ]


def test_search_standards_retries_after_purging_deleted_standard_index_hits(monkeypatch) -> None:
    import tender_backend.api.standards as standards_api

    stale_standard_id = str(uuid4())
    stale_clause_id = str(uuid4())
    live_standard_id = str(uuid4())
    live_clause_id = str(uuid4())
    search_calls = 0
    purged_standard_ids: list[str] = []

    async def fake_search_standard_clauses(
        q: str,
        *,
        specialty: str | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        nonlocal search_calls
        search_calls += 1
        if search_calls == 1:
            return [
                {
                    "standard_id": stale_standard_id,
                    "standard_name": "旧标准",
                    "clause_id": stale_clause_id,
                    "clause_no": "4.4",
                    "summary": "旧索引命中",
                    "page_start": 20,
                    "page_end": 22,
                    "tags": ["排氮"],
                },
            ]
        return [
            {
                "standard_id": live_standard_id,
                "standard_name": "GB 50148-2010",
                "clause_id": live_clause_id,
                "clause_no": "4.4",
                "summary": "有效命中",
                "page_start": 20,
                "page_end": 22,
                "tags": ["排氮"],
            },
        ]

    def fake_get_clauses_by_ids(_conn, clause_ids):
        clause_ids_as_str = [str(clause_id) for clause_id in clause_ids]
        if clause_ids_as_str == [stale_clause_id]:
            return {}
        if clause_ids_as_str == [live_clause_id]:
            return {
                live_clause_id: {
                    "id": live_clause_id,
                    "standard_id": live_standard_id,
                    "standard_name": "GB 50148-2010",
                    "specialty": "电气",
                    "clause_no": "4.4",
                    "page_start": 20,
                    "page_end": 22,
                    "tags": ["排氮"],
                },
            }
        raise AssertionError(clause_ids_as_str)

    def fake_get_standard(_conn, standard_id: UUID):
        if str(standard_id) == stale_standard_id:
            return None
        if str(standard_id) == live_standard_id:
            return {"id": live_standard_id}
        return None

    async def fake_delete_standard_clauses_from_index(*, standard_id: str) -> None:
        purged_standard_ids.append(standard_id)

    monkeypatch.setattr(standards_api, "search_standard_clauses", fake_search_standard_clauses, raising=False)
    monkeypatch.setattr(standards_api._repo, "get_clauses_by_ids", fake_get_clauses_by_ids, raising=False)
    monkeypatch.setattr(standards_api._repo, "get_standard", fake_get_standard, raising=False)
    monkeypatch.setattr(
        standards_api,
        "delete_standard_clauses_from_index",
        fake_delete_standard_clauses_from_index,
        raising=False,
    )

    payload = asyncio.run(
        standards_api.search_standards(q="排氮", specialty=None, top_k=10, conn=object()),
    )

    assert search_calls == 2
    assert purged_standard_ids == [stale_standard_id]
    assert payload == [
        {
            "standard_id": live_standard_id,
            "standard_name": "GB 50148-2010",
            "specialty": "电气",
            "clause_id": live_clause_id,
            "clause_no": "4.4",
            "tags": ["排氮"],
            "summary": "有效命中",
            "page_start": 20,
            "page_end": 22,
        }
    ]
