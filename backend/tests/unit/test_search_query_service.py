from __future__ import annotations

import asyncio
import json

import httpx

from tender_backend.services.search_service import query_service


class _FakeAsyncClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict) -> httpx.Response:
        response = self._responses.pop(0)
        return response


def test_search_clauses_falls_back_when_named_analyzer_missing(monkeypatch) -> None:
    request = httpx.Request("POST", "http://127.0.0.1:9200/clause_index/_search")
    analyzer_missing = httpx.Response(
        400,
        request=request,
        json={
            "error": {
                "root_cause": [
                    {
                        "type": "query_shard_exception",
                        "reason": "[multi_match] analyzer [cn_with_synonym] not found",
                    }
                ]
            }
        },
    )
    fallback_success = httpx.Response(
        200,
        request=request,
        json={
            "hits": {
                "hits": [
                    {
                        "_id": "clause-1",
                        "_score": 1.23,
                        "_source": {
                            "clause_id": "clause-1",
                            "standard_id": "std-1",
                            "standard_name": "示例规范",
                            "clause_no": "5.3.6",
                        },
                    }
                ]
            }
        },
    )
    captured_payloads: list[dict] = []

    class _RecordingClient(_FakeAsyncClient):
        async def post(self, url: str, json: dict) -> httpx.Response:
            captured_payloads.append(json)
            return await super().post(url, json)

    monkeypatch.setattr(
        query_service.httpx,
        "AsyncClient",
        lambda **kwargs: _RecordingClient([analyzer_missing, fallback_success]),
    )

    result = asyncio.run(query_service.search_clauses("接地"))

    assert len(captured_payloads) == 2
    assert captured_payloads[0]["query"]["bool"]["must"][0]["multi_match"]["analyzer"] == "cn_with_synonym"
    assert "analyzer" not in captured_payloads[1]["query"]["bool"]["must"][0]["multi_match"]
    assert result == [
        {
            "_id": "clause-1",
            "_score": 1.23,
            "clause_id": "clause-1",
            "standard_id": "std-1",
            "standard_name": "示例规范",
            "clause_no": "5.3.6",
        }
    ]
