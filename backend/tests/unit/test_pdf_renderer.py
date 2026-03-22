"""Unit tests for vision_service.pdf_renderer."""

from __future__ import annotations

import fitz  # PyMuPDF
import pytest

from tender_backend.services.vision_service.pdf_renderer import (
    PageImage,
    encode_page_base64,
    render_pdf_to_pages,
)


def _create_test_pdf(path: str, *, num_pages: int = 3) -> str:
    """Create a minimal PDF with *num_pages* pages for testing."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((72, 72), f"Page {i + 1}", fontsize=24)
    doc.save(path)
    doc.close()
    return path


class TestRenderPdfToPages:
    def test_renders_all_pages(self, tmp_path):
        pdf = _create_test_pdf(str(tmp_path / "test.pdf"), num_pages=5)
        pages = render_pdf_to_pages(pdf, dpi=72)

        assert len(pages) == 5
        for i, page in enumerate(pages):
            assert page.page_number == i + 1
            assert page.width > 0
            assert page.height > 0
            assert len(page.png_bytes) > 0
            # PNG magic bytes
            assert page.png_bytes[:4] == b"\x89PNG"

    def test_dpi_affects_size(self, tmp_path):
        pdf = _create_test_pdf(str(tmp_path / "test.pdf"), num_pages=1)
        low = render_pdf_to_pages(pdf, dpi=72)[0]
        high = render_pdf_to_pages(pdf, dpi=200)[0]

        assert high.width > low.width
        assert high.height > low.height

    def test_missing_file_raises(self):
        with pytest.raises(Exception):
            render_pdf_to_pages("/nonexistent/file.pdf")


class TestEncodePageBase64:
    def test_produces_valid_data_uri(self, tmp_path):
        pdf = _create_test_pdf(str(tmp_path / "test.pdf"), num_pages=1)
        page = render_pdf_to_pages(pdf, dpi=72)[0]
        uri = encode_page_base64(page)

        assert uri.startswith("data:image/png;base64,")
        # Base64 content should be non-empty
        b64_part = uri.split(",", 1)[1]
        assert len(b64_part) > 10
