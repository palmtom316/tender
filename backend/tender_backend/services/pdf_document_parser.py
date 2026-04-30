"""PDF text parsing for uploaded tender documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF


PDF_PARSER_NAME = "pdf-document-parser"
PDF_PARSER_VERSION = "0.1.0"


class PdfParseError(RuntimeError):
    pass


def _clean_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def parse_pdf_text(path: Path, *, source_file: str) -> list[dict[str, Any]]:
    """Extract text chunks from a text-based PDF.

    Scanned PDFs intentionally produce no chunks here. OCR/MinerU can be layered
    onto the same source_chunk model later without changing downstream consumers.
    """
    try:
        document = fitz.open(str(path))
    except Exception as exc:
        raise PdfParseError(f"Unable to open PDF: {exc}") from exc

    chunks: list[dict[str, Any]] = []
    order = 0
    try:
        for page_index in range(len(document)):
            page_number = page_index + 1
            page = document.load_page(page_index)
            blocks = page.get_text("blocks", sort=True)
            for block_index, block in enumerate(blocks, start=1):
                if len(block) < 5:
                    continue
                text = _clean_text(str(block[4] or ""))
                if not text:
                    continue
                chunks.append(
                    {
                        "chunk_type": "paragraph",
                        "source_file": source_file,
                        "source_locator": f"page:{page_number}:block:{block_index}",
                        "text": text,
                        "page_start": page_number,
                        "page_end": page_number,
                        "sort_order": order,
                        "confidence": 0.95,
                        "metadata_json": {
                            "parser_name": PDF_PARSER_NAME,
                            "parser_version": PDF_PARSER_VERSION,
                            "block_index": block_index,
                            "bbox": [float(value) for value in block[:4]],
                        },
                    }
                )
                order += 1
    finally:
        document.close()

    if not chunks:
        raise PdfParseError("no text extracted from PDF; scanned PDF requires OCR/MinerU processing")

    return chunks
