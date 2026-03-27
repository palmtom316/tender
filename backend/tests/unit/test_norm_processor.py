from __future__ import annotations

import threading
from uuid import uuid4

from tender_backend.services.norm_service import norm_processor


def test_index_clauses_succeeds_from_thread_without_event_loop(monkeypatch) -> None:
    calls: list[tuple[str, list[tuple[str, dict]]]] = []

    class FakeIndexManager:
        async def bulk_index(self, index: str, docs: list[tuple[str, dict]]) -> int:
            calls.append((index, docs))
            return len(docs)

    monkeypatch.setattr(norm_processor, "IndexManager", FakeIndexManager)
    monkeypatch.setattr(
        norm_processor.asyncio,
        "get_event_loop",
        lambda: (_ for _ in ()).throw(RuntimeError("There is no current event loop")),
    )
    monkeypatch.setattr(
        norm_processor,
        "build_clause_index_docs",
        lambda standard, clauses: [("doc-1", {"standard_id": str(standard["id"])})],
    )

    error: list[Exception] = []

    def worker() -> None:
        try:
            norm_processor._index_clauses(
                {"id": uuid4(), "standard_code": "GB 50148-2010", "standard_name": "测试规范"},
                [{"id": uuid4(), "clause_no": "4.7.2"}],
            )
        except Exception as exc:  # pragma: no cover - failure path for assertion
            error.append(exc)

    thread = threading.Thread(target=worker, name="norm-index-test")
    thread.start()
    thread.join()

    assert error == []
    assert len(calls) == 1
    assert calls[0][0] == "clause_index"
