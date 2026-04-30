"""MinerU-backed PDF parsing for uploaded tender documents."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from tender_backend.services.parse_service.mineru_client import MineruClient, MineruRequestOptions
from tender_backend.services.parse_service.task_poller import poll_until_complete


PDF_PARSER_NAME = "mineru"
PDF_PARSER_VERSION = "v4-batch"


class PdfParseError(RuntimeError):
    pass


def _clean_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def chunks_from_mineru_result(result: Any, *, source_file: str) -> list[dict[str, Any]]:
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
                    "parser_name": PDF_PARSER_NAME,
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
                    "parser_name": PDF_PARSER_NAME,
                    "parser_version": result.raw_payload.get("parser_version"),
                    "job_id": result.job_id,
                    "table_index": table_index,
                    "extraction_method": "mineru_table",
                },
            }
        )
        order += 1
    return chunks


async def parse_pdf_with_mineru(path: Path, *, source_file: str) -> list[dict[str, Any]]:
    """Parse every tender PDF through the same MinerU v4 batch API used for standards."""

    api_key = os.environ.get("MINERU_API_KEY", "").strip()
    if not api_key:
        raise PdfParseError("PDF parsing requires MinerU but MINERU_API_KEY is not configured")
    client = MineruClient(
        api_key=api_key,
        options=MineruRequestOptions(enable_table=True, is_ocr=True),
    )
    upload = await client.request_upload_url(path.name, data_id=source_file)
    await client.upload_file(upload.upload_url, path.read_bytes(), content_type="application/pdf")
    result = await poll_until_complete(client, upload.batch_id)
    if result.status != "completed":
        raise PdfParseError(f"MinerU PDF parsing failed: {result.raw_payload}")
    chunks = chunks_from_mineru_result(result, source_file=source_file)
    if not chunks:
        raise PdfParseError("MinerU PDF parsing completed but returned no parseable chunks")
    return chunks


def parse_pdf_text(path: Path, *, source_file: str) -> list[dict[str, Any]]:
    """Compatibility wrapper for callers outside an event loop."""

    try:
        return asyncio.run(parse_pdf_with_mineru(path, source_file=source_file))
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" not in str(exc):
            raise
        raise PdfParseError("Use parse_pdf_with_mineru from async API handlers") from exc
