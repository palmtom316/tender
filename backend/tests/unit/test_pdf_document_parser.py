from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest

from tender_backend.services.pdf_document_parser import PdfParseError, _chunks_from_mineru_result, parse_pdf_text


def _write_pdf(path: Path, pages: list[str]) -> None:
    document = fitz.open()
    try:
        for text in pages:
            page = document.new_page()
            page.insert_text((72, 72), text)
        document.save(path)
    finally:
        document.close()


def test_parse_pdf_text_preserves_page_locator(tmp_path: Path) -> None:
    pdf_path = tmp_path / "tender.pdf"
    _write_pdf(pdf_path, ["Project name: test tender", "Bid deadline: 2026-05-01"])

    chunks = parse_pdf_text(pdf_path, source_file="tender.pdf")

    assert len(chunks) == 2
    assert chunks[0]["source_locator"].startswith("page:1:block:")
    assert chunks[0]["page_start"] == 1
    assert chunks[0]["page_end"] == 1
    assert "test tender" in chunks[0]["text"]
    assert chunks[1]["page_start"] == 2


def test_parse_pdf_table_preserves_page_locator(tmp_path: Path) -> None:
    pdf_path = tmp_path / "table.pdf"
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 60), "评分表")
        cells = [
            (72, 100, 180, 130, "评分项"),
            (180, 100, 260, 130, "分值"),
            (72, 130, 180, 160, "施工方案"),
            (180, 130, 260, 160, "20"),
        ]
        for x0, y0, x1, y1, text in cells:
            page.draw_rect(fitz.Rect(x0, y0, x1, y1))
            page.insert_text((x0 + 4, y0 + 18), text)
        document.save(pdf_path)
    finally:
        document.close()

    chunks = parse_pdf_text(pdf_path, source_file="table.pdf")
    tables = [chunk for chunk in chunks if chunk["chunk_type"] == "table"]

    assert tables
    assert tables[0]["source_locator"].startswith("page:1:table:")
    assert tables[0]["page_start"] == 1
    assert tables[0]["page_end"] == 1


def test_scanned_pdf_without_mineru_key_reports_ocr_requirement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "scan.pdf"
    document = fitz.open()
    try:
        document.new_page()
        document.save(pdf_path)
    finally:
        document.close()
    monkeypatch.delenv("MINERU_API_KEY", raising=False)

    with pytest.raises(PdfParseError, match="MINERU_API_KEY"):
        parse_pdf_text(pdf_path, source_file="scan.pdf")


def test_mineru_result_converts_pages_and_tables_to_chunks() -> None:
    class _Result:
        job_id = "job-1"
        pages = [{"page_number": 1, "markdown": "OCR 文本"}]
        tables = [{"page_start": 2, "page_end": 2, "table_title": "表1", "table_html": "<table><tr><td>A</td></tr></table>", "raw_json": {}}]
        raw_payload = {"parser_version": "2.7"}

    chunks = _chunks_from_mineru_result(_Result(), source_file="scan.pdf")

    assert chunks[0]["source_locator"] == "page:1:mineru"
    assert chunks[1]["source_locator"] == "page:2:mineru-table:1"
    assert chunks[1]["chunk_type"] == "table"
