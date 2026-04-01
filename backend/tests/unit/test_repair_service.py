from __future__ import annotations

import httpx

from tender_backend.services.norm_service.repair_tasks import RepairTask
from tender_backend.services.vision_service.pdf_renderer import PageImage
from tender_backend.services.vision_service.repair_service import run_repair_tasks


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "content": (
                '{"task_type":"table_repair","source_ref":"table:t1","status":"patched",'
                '"patched_table_html":"<table></table>","notes":"ok"}'
            )
        }


class _FakeStatusSequenceResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.request = httpx.Request("POST", "http://127.0.0.1:8100/api/ai/chat")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self) -> dict[str, object]:
        return {
            "content": (
                '{"task_type":"table_repair","source_ref":"table:t1","status":"patched",'
                '"patched_table_html":"<table></table>","notes":"ok"}'
            )
        }


def test_run_repair_tasks_uses_local_repair_task_type(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url, json, timeout):
        captured["payload"] = json
        return _FakeResponse()

    monkeypatch.setattr(
        "tender_backend.services.vision_service.repair_service._get_pdf_path",
        lambda conn, document_id: "/tmp/test.pdf",
    )
    monkeypatch.setattr(
        "tender_backend.services.vision_service.repair_service.render_pdf_page_range",
        lambda pdf_path, page_start, page_end=None, dpi=200: [
            PageImage(page_number=page_start, png_bytes=b"png", width=10, height=10)
        ],
    )
    monkeypatch.setattr(
        "tender_backend.services.vision_service.repair_service.httpx.post",
        fake_post,
    )

    result = run_repair_tasks(
        conn=object(),
        document_id="doc-1",
        tasks=[
            RepairTask(
                task_type="table_repair",
                source_ref="table:t1",
                page_start=2,
                page_end=2,
                input_payload={},
                trigger_reasons=["table.high_recall"],
            )
        ],
    )

    assert result[0].task_type == "table_repair"
    assert result[0].source_ref == "table:t1"
    assert result[0].patched_table_html == "<table></table>"
    assert "primary_override" not in captured["payload"]
    assert "fallback_override" not in captured["payload"]


def test_run_repair_tasks_retries_transient_502_before_succeeding(monkeypatch) -> None:
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    monkeypatch.setattr(
        "tender_backend.services.vision_service.repair_service._get_pdf_path",
        lambda conn, document_id: "/tmp/test.pdf",
    )
    monkeypatch.setattr(
        "tender_backend.services.vision_service.repair_service.render_pdf_page_range",
        lambda pdf_path, page_start, page_end=None, dpi=200: [
            PageImage(page_number=page_start, png_bytes=b"png", width=10, height=10)
        ],
    )
    def fake_post(url, json, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            return _FakeStatusSequenceResponse(502)
        return _FakeStatusSequenceResponse(200)

    monkeypatch.setattr(
        "tender_backend.services.vision_service.repair_service.httpx.post",
        fake_post,
    )
    monkeypatch.setattr(
        "tender_backend.services.vision_service.repair_service.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    result = run_repair_tasks(
        conn=object(),
        document_id="doc-1",
        tasks=[
            RepairTask(
                task_type="table_repair",
                source_ref="table:t1",
                page_start=2,
                page_end=2,
                input_payload={},
                trigger_reasons=["table.high_recall"],
            )
        ],
    )

    assert attempts["count"] == 3
    assert sleep_calls == [1.0, 2.0]
    assert result[0].patched_table_html == "<table></table>"
