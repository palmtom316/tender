from __future__ import annotations

import asyncio
from uuid import uuid4

import tender_backend.workflows.export_bid as export_bid_module
from tender_backend.api import exports as exports_api
from tender_backend.services.export_service.docx_exporter import (
    EXPORT_MODE_MULTI_DOC_ZIP,
    EXPORT_MODE_MULTI_DOCX_ZIP,
    EXPORT_MODE_SINGLE_DOCX,
)
from tender_backend.workflows.base import WorkflowContext
from tender_backend.workflows.states import StepState


class _FakeConn:
    def execute(self, *args, **kwargs):
        return None

    def commit(self):
        return None


def _make_ctx(mode: str | None) -> WorkflowContext:
    data = {"_db_conn": _FakeConn()}
    if mode is not None:
        data["export_mode"] = mode
    return WorkflowContext(project_id=str(uuid4()), data=data)


def test_render_docx_step_uses_export_mode(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_render_export(conn, *, project_id, mode, template_name):
        captured["mode"] = mode
        captured["template_name"] = template_name
        return f"/tmp/{mode}.zip"

    monkeypatch.setattr(
        "tender_backend.services.export_service.docx_exporter.render_export",
        fake_render_export,
    )

    step = export_bid_module.RenderDocx()
    ctx = _make_ctx(EXPORT_MODE_MULTI_DOCX_ZIP)

    result = asyncio.run(step.execute(ctx))

    assert result.state == StepState.COMPLETED
    assert captured["mode"] == EXPORT_MODE_MULTI_DOCX_ZIP
    assert ctx.data["docx_path"] == "/tmp/multi_docx_zip.zip"
    assert ctx.data["export_mode"] == EXPORT_MODE_MULTI_DOCX_ZIP


def test_render_docx_step_rejects_unknown_mode() -> None:
    step = export_bid_module.RenderDocx()
    ctx = _make_ctx("nonsense")

    result = asyncio.run(step.execute(ctx))

    assert result.state == StepState.FAILED
    assert "unsupported export mode" in result.message


def test_convert_to_pdf_step_skips_for_zip_modes() -> None:
    step = export_bid_module.ConvertToPdf()
    ctx = _make_ctx(EXPORT_MODE_MULTI_DOC_ZIP)
    ctx.data["docx_path"] = "/tmp/some.zip"

    result = asyncio.run(step.execute(ctx))

    assert result.state == StepState.COMPLETED
    assert ctx.data["pdf_path"] is None


def test_convert_to_pdf_step_runs_for_single_mode(monkeypatch) -> None:
    step = export_bid_module.ConvertToPdf()
    ctx = _make_ctx(EXPORT_MODE_SINGLE_DOCX)
    ctx.data["docx_path"] = "/tmp/doc.docx"

    monkeypatch.setattr(
        "tender_backend.services.export_service.pdf_exporter.convert_docx_to_pdf",
        lambda path: path.with_suffix(".pdf"),
    )

    result = asyncio.run(step.execute(ctx))

    assert result.state == StepState.COMPLETED
    assert ctx.data["pdf_path"] == "/tmp/doc.pdf"


def test_template_name_to_mode_round_trip() -> None:
    assert exports_api._template_name_to_mode("plain_docx") == EXPORT_MODE_SINGLE_DOCX
    assert exports_api._template_name_to_mode("chapter_docx_zip") == EXPORT_MODE_MULTI_DOCX_ZIP
    assert exports_api._template_name_to_mode("chapter_doc_zip") == EXPORT_MODE_MULTI_DOC_ZIP
    assert exports_api._template_name_to_mode(None) == EXPORT_MODE_SINGLE_DOCX
    assert exports_api._template_name_to_mode("unknown") == EXPORT_MODE_SINGLE_DOCX
