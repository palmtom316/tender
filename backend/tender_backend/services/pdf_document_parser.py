"""PDF parsing for uploaded tender documents."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from tender_backend.services.parse_service.mineru_client import MineruClient, MineruRequestOptions
from tender_backend.services.parse_service.task_poller import poll_until_complete


PDF_PARSER_NAME = "pdf-document-parser"
PDF_PARSER_VERSION = "0.2.0"


class PdfParseError(RuntimeError):
    pass


def _clean_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def _rows_from_pdf_table(table: Any) -> list[list[str]]:
    try:
        rows = table.extract()
    except Exception:
        rows = []
    normalized: list[list[str]] = []
    for row in rows or []:
        values = [_clean_text(str(cell or "")) for cell in row]
        if any(values):
            normalized.append(values)
    return normalized


def _table_chunks_from_page(page: Any, *, source_file: str, page_number: int, start_order: int) -> list[dict[str, Any]]:
    finder = getattr(page, "find_tables", None)
    if finder is None:
        return []
    try:
        tables = finder()
    except Exception:
        return []
    chunks: list[dict[str, Any]] = []
    for table_index, table in enumerate(getattr(tables, "tables", []) or [], start=1):
        rows = _rows_from_pdf_table(table)
        if not rows:
            continue
        bbox = [float(value) for value in getattr(table, "bbox", []) or []]
        chunks.append(
            {
                "chunk_type": "table",
                "source_file": source_file,
                "source_locator": f"page:{page_number}:table:{table_index}",
                "title": rows[0][0] if rows and rows[0] else None,
                "text": "\n".join("\t".join(row) for row in rows),
                "table_json": {
                    "headers": rows[0] if rows else [],
                    "rows": rows,
                    "bbox": bbox,
                },
                "page_start": page_number,
                "page_end": page_number,
                "sort_order": start_order + len(chunks),
                "confidence": 0.82,
                "metadata_json": {
                    "parser_name": PDF_PARSER_NAME,
                    "parser_version": PDF_PARSER_VERSION,
                    "table_index": table_index,
                    "bbox": bbox,
                    "extraction_method": "pymupdf_find_tables",
                },
            }
        )
    return chunks


def _chunks_from_mineru_result(result: Any, *, source_file: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    order = 0
    for page in result.pages:
        page_number = page.get("page_number")
        text = _clean_text(str(page.get("markdown") or ""))
        if not text:
            continue
        chunks.append(
            {
                "chunk_type": "paragraph",
                "source_file": source_file,
                "source_locator": f"page:{page_number}:mineru",
                "text": text,
                "page_start": page_number,
                "page_end": page_number,
                "sort_order": order,
                "confidence": 0.86,
                "metadata_json": {
                    "parser_name": "mineru",
                    "parser_version": result.raw_payload.get("parser_version"),
                    "job_id": result.job_id,
                    "extraction_method": "mineru_ocr",
                },
            }
        )
        order += 1
    for table_index, table in enumerate(result.tables, start=1):
        html = str(table.get("table_html") or "")
        title = table.get("table_title")
        page_start = table.get("page_start")
        chunks.append(
            {
                "chunk_type": "table",
                "source_file": source_file,
                "source_locator": f"page:{page_start}:mineru-table:{table_index}",
                "title": title,
                "text": html,
                "table_json": {
                    "table_title": title,
                    "table_html": html,
                    "raw_json": table.get("raw_json"),
                },
                "page_start": page_start,
                "page_end": table.get("page_end") or page_start,
                "sort_order": order,
                "confidence": 0.86,
                "metadata_json": {
                    "parser_name": "mineru",
                    "parser_version": result.raw_payload.get("parser_version"),
                    "job_id": result.job_id,
                    "table_index": table_index,
                    "extraction_method": "mineru_table",
                },
            }
        )
        order += 1
    return chunks


async def _parse_pdf_with_mineru_async(path: Path, *, source_file: str) -> list[dict[str, Any]]:
    api_key = os.environ.get("MINERU_API_KEY", "").strip()
    if not api_key:
        raise PdfParseError("scanned PDF requires OCR/MinerU processing but MINERU_API_KEY is not configured")
    client = MineruClient(
        api_key=api_key,
        options=MineruRequestOptions(enable_table=True, is_ocr=True),
    )
    upload = await client.request_upload_url(path.name, data_id=source_file)
    await client.upload_file(upload.upload_url, path.read_bytes(), content_type="application/pdf")
    result = await poll_until_complete(client, upload.batch_id)
    if result.status != "completed":
        raise PdfParseError(f"MinerU OCR failed: {result.raw_payload}")
    chunks = _chunks_from_mineru_result(result, source_file=source_file)
    if not chunks:
        raise PdfParseError("MinerU OCR completed but returned no parseable chunks")
    return chunks


def parse_pdf_with_mineru(path: Path, *, source_file: str) -> list[dict[str, Any]]:
    try:
        return asyncio.run(_parse_pdf_with_mineru_async(path, source_file=source_file))
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" not in str(exc):
            raise
        raise PdfParseError("MinerU OCR cannot run inside an active event loop") from exc


def parse_pdf_text(path: Path, *, source_file: str) -> list[dict[str, Any]]:
    """Extract text and table chunks from a PDF; scanned PDFs fall back to MinerU OCR."""
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
            table_chunks = _table_chunks_from_page(page, source_file=source_file, page_number=page_number, start_order=order)
            chunks.extend(table_chunks)
            order += len(table_chunks)
    finally:
        document.close()

    if not chunks:
        return parse_pdf_with_mineru(path, source_file=source_file)

    return chunks
