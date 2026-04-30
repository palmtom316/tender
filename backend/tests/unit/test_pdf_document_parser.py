from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from tender_backend.services.pdf_document_parser import parse_pdf_text


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
