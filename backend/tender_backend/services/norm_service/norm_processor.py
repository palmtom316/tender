"""Orchestrator: MinerU parse → compress → split → per-scope AI → merge → validate → persist + index.

This is the core processing pipeline for standard PDFs.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from html import unescape
from html.parser import HTMLParser
from dataclasses import replace
from io import BytesIO
from uuid import UUID
from zipfile import ZipFile

import httpx
import structlog
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.core.config import get_settings
from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.block_segments import BlockSegment, build_single_standard_blocks
from tender_backend.services.norm_service.document_assets import build_document_asset
from tender_backend.services.norm_service.outline_rebuilder import collect_outline_clause_nos_from_pages
from tender_backend.services.norm_service.repair_tasks import build_repair_tasks
from tender_backend.services.norm_service.ast_merger import merge_repair_patches
from tender_backend.services.norm_service.prompt_builder import build_prompt
from tender_backend.services.norm_service.scope_splitter import ProcessingScope, rebalance_scopes
from tender_backend.services.norm_service.structural_nodes import build_processing_scopes as build_structured_processing_scopes
from tender_backend.services.norm_service.tree_builder import build_tree, link_commentary, validate_tree
from tender_backend.services.norm_service.validation import validate_clauses
from tender_backend.services.search_service.index_manager import IndexManager
from tender_backend.services.storage_service.project_file_storage import ProjectFileStorage
from tender_backend.services.vision_service.repair_service import run_repair_tasks
from tender_backend.tools.reindex_standard_clauses import build_clause_index_docs

logger = structlog.stdlib.get_logger(__name__)

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:8001")
_MAX_SCOPE_RETRY_ATTEMPTS = 2
_SINGLE_STANDARD_BLOCK_EXPERIMENT_IDS = {
    UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a"),
}

_std_repo = StandardRepository()
_agent_repo = AgentConfigRepository()
_storage = ProjectFileStorage()


# ── MinerU OCR integration ──

def _get_pdf_path(conn: Connection, document_id: str) -> str | None:
    """Look up the local file path for a document's source PDF."""
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """SELECT pf.storage_key
               FROM document d
               JOIN project_file pf ON pf.id = d.project_file_id
               WHERE d.id = %s""",
            (document_id,),
        ).fetchone()
    if not row:
        return None

    resolved = _storage.resolve_local_path(row["storage_key"])
    return str(resolved) if resolved else None


def _mineru_api_root(base_url: str) -> str:
    """Normalize MinerU OCR endpoint into the v4 API root."""
    normalized = base_url.rstrip("/")
    for suffix in ("/extract/task", "/extract/task/", "/parse", "/parse/"):
        if normalized.endswith(suffix.rstrip("/")):
            return normalized[: -len(suffix.rstrip("/"))]
    return normalized


def _ai_gateway_chat_url(base_url: str) -> str:
    """Build the AI Gateway chat endpoint with a single /api prefix."""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api"):
        return f"{normalized}/ai/chat"
    return f"{normalized}/api/ai/chat"


def _ai_gateway_timeout_seconds(model_name: str | None) -> float:
    """Use a longer timeout for reasoning models, which stream much slower."""
    settings = get_settings()
    base_timeout = settings.standard_ai_gateway_timeout_seconds
    if model_name and "reasoner" in model_name.lower():
        return max(base_timeout, 300.0)
    return base_timeout


def _scope_delay_seconds() -> float:
    settings = get_settings()
    delay = max(0.0, settings.standard_ai_scope_delay_ms / 1000.0)
    jitter = max(0.0, settings.standard_ai_scope_delay_jitter_ms / 1000.0)
    if jitter:
        delay += random.uniform(0.0, jitter)
    return delay


def _extract_markdown_from_zip(content: bytes) -> str:
    """Read the primary markdown file from a MinerU result zip."""
    with ZipFile(BytesIO(content)) as zf:
        names = zf.namelist()
        for candidate in ("full.md", "result/full.md", "output/full.md"):
            if candidate in names:
                return zf.read(candidate).decode("utf-8")

        for name in names:
            if name.endswith(".md"):
                return zf.read(name).decode("utf-8")

    raise RuntimeError("MinerU result zip does not contain a markdown file")


def _extract_pages_from_payload(payload: object) -> list[dict]:
    """Best-effort extraction of page-level OCR payloads from MinerU JSON."""
    def _looks_like_page_payload(item: dict) -> bool:
        page_keys = {"page_number", "page_no", "page_num", "page"}
        text_keys = {"markdown", "md", "raw_markdown", "raw_text"}
        return bool(page_keys.intersection(item.keys()) or text_keys.intersection(item.keys()))

    def _looks_like_layout_block(item: dict) -> bool:
        if not isinstance(item, dict):
            return False
        return (
            ("page_idx" in item or "page_index" in item)
            and "type" in item
            and any(key in item for key in ("text", "content", "table_body", "table_caption", "table_footnote"))
        )

    def _aggregate_layout_blocks(items: list[dict]) -> list[dict]:
        grouped: dict[int, list[dict]] = {}
        for item in items:
            page_idx = item.get("page_idx")
            if not isinstance(page_idx, int):
                page_idx = item.get("page_index")
            if not isinstance(page_idx, int):
                continue
            grouped.setdefault(page_idx, []).append(item)

        aggregated: list[dict] = []
        for page_idx in sorted(grouped):
            blocks = sorted(
                grouped[page_idx],
                key=lambda block: (
                    (block.get("bbox") or [0, 0, 0, 0])[1],
                    (block.get("bbox") or [0, 0, 0, 0])[0],
                ),
            )
            markdown = "\n".join(
                fragment.strip()
                for block in blocks
                for fragment in _collect_text_fragments(block)
                if fragment.strip()
            )
            if not markdown.strip():
                continue
            aggregated.append({
                "page_number": page_idx + 1,
                "markdown": markdown,
            })
        return aggregated

    def _aggregate_page_block_lists(items: list[list[dict]]) -> list[dict]:
        aggregated: list[dict] = []
        for page_index, blocks in enumerate(items, start=1):
            ordered_blocks = sorted(
                blocks,
                key=lambda block: (
                    (block.get("bbox") or [0, 0, 0, 0])[1],
                    (block.get("bbox") or [0, 0, 0, 0])[0],
                ),
            )
            markdown = "\n".join(
                fragment.strip()
                for block in ordered_blocks
                for fragment in _collect_text_fragments(block)
                if fragment.strip()
            )
            if not markdown.strip():
                continue
            aggregated.append({
                "page_number": page_index,
                "markdown": markdown,
            })
        return aggregated

    if isinstance(payload, list):
        if payload and all(isinstance(item, list) for item in payload):
            page_block_lists = [item for item in payload if all(isinstance(block, dict) for block in item)]
            pages = _aggregate_page_block_lists(page_block_lists)
            if pages:
                return pages
        if payload and all(isinstance(item, dict) for item in payload):
            if all(_looks_like_layout_block(item) for item in payload):
                pages = _aggregate_layout_blocks(payload)
                if pages:
                    return pages
            if any(_looks_like_page_payload(item) for item in payload):
                return payload
        for item in payload:
            pages = _extract_pages_from_payload(item)
            if pages:
                return pages
        return []

    if isinstance(payload, dict):
        for key in ("pages", "page_infos", "page_info", "page_results", "data", "result"):
            if key in payload:
                pages = _extract_pages_from_payload(payload[key])
                if pages:
                    return pages
        for value in payload.values():
            pages = _extract_pages_from_payload(value)
            if pages:
                return pages

    return []


def _extract_pages_from_zip(content: bytes) -> list[dict]:
    """Read page-level OCR payloads from a MinerU result zip when available."""
    with ZipFile(BytesIO(content)) as zf:
        for name in zf.namelist():
            if not name.endswith(".json"):
                continue
            try:
                payload = json.loads(zf.read(name).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            pages = _extract_pages_from_payload(payload)
            if pages:
                return pages
    return []


def _extract_tables_from_payload(payload: object) -> list[dict]:
    """Best-effort extraction of table payloads from MinerU JSON."""
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            if any(
                isinstance(item.get("html"), str)
                or isinstance(item.get("table_html"), str)
                or isinstance(item.get("cells"), list)
                for item in payload
            ):
                return payload
        for item in payload:
            tables = _extract_tables_from_payload(item)
            if tables:
                return tables
        return []

    if isinstance(payload, dict):
        for key in ("tables", "table_infos", "table_info", "table_results", "data", "result"):
            if key in payload:
                tables = _extract_tables_from_payload(payload[key])
                if tables:
                    return tables
        for value in payload.values():
            tables = _extract_tables_from_payload(value)
            if tables:
                return tables

    return []


def _extract_tables_from_zip(content: bytes) -> list[dict]:
    with ZipFile(BytesIO(content)) as zf:
        for name in zf.namelist():
            if not name.endswith(".json"):
                continue
            try:
                payload = json.loads(zf.read(name).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            tables = _extract_tables_from_payload(payload)
            if tables:
                return tables
    return []


def _normalize_tables(tables: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for table in tables:
        page = table.get("page")
        if not isinstance(page, int):
            page = table.get("page_number")
        normalized.append({
            "page": page,
            "page_start": table.get("page_start", page),
            "page_end": table.get("page_end", page),
            "table_title": table.get("table_title") or table.get("title"),
            "table_html": table.get("table_html") or table.get("html"),
            "data": table,
        })
    return normalized


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_page_number(page: dict, index: int) -> int:
    for key in ("page_number", "page_no", "page_num", "page"):
        value = page.get(key)
        if isinstance(value, int) and value > 0:
            return value
    for key in ("page_idx", "page_index"):
        value = page.get(key)
        if isinstance(value, int) and value >= 0:
            return value + 1
    return index + 1


def _collect_text_fragments(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        fragments: list[str] = []
        for item in value:
            fragments.extend(_collect_text_fragments(item))
        return fragments
    if isinstance(value, dict):
        fragments: list[str] = []
        for key in (
            "markdown",
            "md",
            "text",
            "content",
            "raw_text",
            "raw_markdown",
            "title_content",
            "paragraph_content",
            "page_header_content",
            "page_footer_content",
            "table_caption",
            "table_footnote",
        ):
            if key in value:
                fragments.extend(_collect_text_fragments(value[key]))
        if fragments:
            return fragments
        for nested in value.values():
            fragments.extend(_collect_text_fragments(nested))
        return fragments
    return []


def _extract_page_text(page: dict) -> str:
    return "\n".join(
        fragment.strip()
        for fragment in _collect_text_fragments(page)
        if fragment.strip()
    )


def _normalize_pages(pages: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for index, page in enumerate(pages):
        text = _normalize_match_text(_extract_page_text(page))
        if not text:
            continue
        normalized.append({
            "page_number": _extract_page_number(page, index),
            "text": text,
            "raw_page": page,
        })
    return normalized


def _find_section_page_index(
    pages: list[dict],
    *,
    heading: str,
    chunk: str,
    start_index: int,
) -> int | None:
    if not pages:
        return None

    body = chunk.split("\n", 1)[1] if "\n" in chunk else chunk
    candidates = [
        _normalize_match_text(heading),
        _normalize_match_text(chunk[:160]),
        _normalize_match_text(body[:120]),
    ]
    candidates = [candidate for candidate in candidates if candidate]

    for search_start in (start_index, 0):
        for index in range(search_start, len(pages)):
            page_text = pages[index]["text"]
            if any(candidate in page_text for candidate in candidates):
                return index
    return None


def _raise_mineru_http_error(exc: httpx.HTTPStatusError) -> None:
    """Translate upstream MinerU HTTP errors into actionable messages."""
    if exc.response.status_code == 413:
        raise RuntimeError(
            "MinerU 拒绝了当前解析请求。当前服务端已改为 batch 上传模式；"
            "如果仍看到这个错误，请检查 MinerU 侧文件大小限制或上传接口配置。"
        ) from exc
    if exc.response.status_code == 403:
        raise RuntimeError(
            "MinerU request failed: HTTP 403。请检查 MinerU API Key 是否有效，"
            "以及预签名上传请求是否未附带额外请求头。"
        ) from exc
    raise RuntimeError(f"MinerU request failed: HTTP {exc.response.status_code}") from exc


def _parse_via_mineru(conn: Connection, document_id: str) -> int:
    """Submit PDF to MinerU OCR, poll for result, persist sections.

    Returns the number of sections persisted.
    """
    from tender_backend.services.parse_service.parser import (
        persist_sections,
        persist_tables,
        update_document_parse_assets,
    )

    config = _agent_repo.get_by_key(conn, "parse")
    if not config or not config.enabled or not config.api_key:
        raise RuntimeError("MinerU (parse) agent not configured or disabled. "
                           "Please configure OCR credentials in Settings.")

    pdf_path = _get_pdf_path(conn, document_id)
    if not pdf_path or not os.path.isfile(pdf_path):
        raise FileNotFoundError(
            f"PDF file not found at {pdf_path}. Please re-upload the standard."
        )

    base_url = (config.base_url or "").rstrip("/")
    api_root = _mineru_api_root(base_url)
    headers = {"Authorization": f"Bearer {config.api_key}"}

    # Step 1: Ask MinerU for a batch upload URL.
    logger.info("mineru_requesting_upload_url", document_id=document_id, url=api_root)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    request_payload = {
        "files": [{
            "name": os.path.basename(pdf_path),
            "data_id": document_id,
        }],
        "model_version": "vlm",
        "is_ocr": True,
        "enable_table": True,
        "language": "ch",
    }
    try:
        resp = httpx.post(
            f"{api_root}/file-urls/batch",
            json=request_payload,
            headers=headers,
            timeout=60.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _raise_mineru_http_error(exc)
    batch_data = resp.json()

    data = batch_data.get("data", {})
    batch_id = data.get("batch_id")
    upload_urls = data.get("file_urls") or data.get("upload_urls") or []
    if not batch_id or not upload_urls:
        logger.warning("mineru_upload_url_response_format", data=batch_data)
        raise RuntimeError(f"MinerU did not return batch upload URLs: {batch_data}")

    upload_url = upload_urls[0]
    logger.info("mineru_uploading_file", batch_id=batch_id, upload_url=upload_url)
    try:
        upload_resp = httpx.put(
            upload_url,
            data=pdf_bytes,
            timeout=120.0,
        )
        upload_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _raise_mineru_http_error(exc)

    # Step 2: Poll batch result until completion.
    result_url = f"{api_root}/extract-results/batch/{batch_id}"
    max_wait = 600
    poll_interval = 5
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        resp = httpx.get(result_url, headers=headers, timeout=30.0)
        if resp.status_code == 404:
            continue  # Not ready yet
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_mineru_http_error(exc)
        result = resp.json()

        result_items = result.get("data", {}).get("extract_result") or result.get("extract_result") or []
        if not result_items:
            logger.info("mineru_poll_waiting", batch_id=batch_id, elapsed=elapsed)
            continue

        item = result_items[0]
        status = item.get("state") or item.get("status") or ""
        logger.info("mineru_poll", batch_id=batch_id, status=status, elapsed=elapsed)

        if status in ("done", "completed", "success"):
            full_zip_url = (
                item.get("full_zip_url")
                or item.get("result_zip_url")
                or item.get("zip_url")
            )
            if not full_zip_url:
                raise RuntimeError(f"MinerU did not return a result zip URL: {item}")

            zip_resp = httpx.get(full_zip_url, timeout=60.0)
            try:
                zip_resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _raise_mineru_http_error(exc)
            raw_content = _extract_markdown_from_zip(zip_resp.content)
            pages = (
                _extract_pages_from_zip(zip_resp.content)
                or _extract_pages_from_payload(item.get("pages") or [])
            )
            tables = (
                _extract_tables_from_zip(zip_resp.content)
                or _extract_tables_from_payload(item.get("tables") or [])
            )

            sections = _mineru_to_sections(raw_content, pages)
            update_document_parse_assets(
                conn,
                document_id=UUID(document_id),
                parser_name="mineru",
                raw_payload={
                    "pages": pages,
                    "tables": tables,
                    "full_markdown": raw_content,
                    "batch_id": batch_id,
                    "result_item": item,
                },
            )
            normalized_tables = _normalize_tables(tables)
            if normalized_tables:
                persist_tables(conn, document_id=UUID(document_id), tables=normalized_tables)
            count = persist_sections(conn, document_id=UUID(document_id), sections=sections)
            logger.info("mineru_sections_persisted", document_id=document_id, count=count)
            return count

        if status in ("failed", "error"):
            error_msg = item.get("err_msg") or item.get("error") or "Unknown MinerU error"
            raise RuntimeError(f"MinerU parsing failed: {error_msg}")

    raise TimeoutError(f"MinerU parsing timed out after {max_wait}s for batch {batch_id}")


def _mineru_to_sections(content: str, pages: list[dict]) -> list[dict]:
    """Convert MinerU markdown content to section dicts for persist_sections."""
    import re

    if not content:
        return []

    sections: list[dict] = []
    normalized_pages = _normalize_pages(pages)
    page_cursor = 0
    # Split by heading patterns: # Title, ## Title, ### Title, etc.
    # or numeric headings like "1 总则", "3.2 构件"
    heading_pattern = re.compile(
        r"^(#{1,6})\s+(.+)$|^(\d+(?:\.\d+)*)\s+(\S.*)$",
        re.MULTILINE,
    )
    matches = list(heading_pattern.finditer(content))

    if not matches:
        # No headings found — treat entire content as one section
        sections.append({
            "section_code": None,
            "title": "全文",
            "level": 1,
            "page_start": 1,
            "page_end": None,
            "text": content.strip(),
        })
        return sections

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        chunk = content[start:end].strip()

        if m.group(1):  # Markdown heading
            level = len(m.group(1))
            title = m.group(2).strip()
            code = None
        else:  # Numeric heading
            code = m.group(3)
            title = m.group(4).strip()
            level = len(code.split("."))

        # Text is everything after the heading line
        lines = chunk.split("\n", 1)
        text = lines[1].strip() if len(lines) > 1 else ""
        heading = lines[0].strip() if lines else title
        page_index = _find_section_page_index(
            normalized_pages,
            heading=heading,
            chunk=chunk,
            start_index=page_cursor,
        )
        page_number = None
        page_payload = None
        if page_index is not None:
            page_cursor = page_index
            page_number = normalized_pages[page_index]["page_number"]
            page_payload = normalized_pages[page_index]["raw_page"]

        sections.append(_coerce_inline_clause_text({
            "section_code": code,
            "title": title,
            "level": level,
            "page_start": page_number,
            "page_end": page_number,
            "text": text,
            "text_source": "mineru_markdown",
            "sort_order": i,
            "raw_json": page_payload,
        }))

    return sections


# ── Section fetching ──

def _fetch_sections(conn: Connection, document_id: str) -> list[dict]:
    """Fetch all document_section rows for a document."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT id, section_code, title, level, text,
                      raw_json, text_source, sort_order,
                      page_start, page_end
               FROM document_section
               WHERE document_id = %s
               ORDER BY
                   CASE WHEN page_start IS NULL THEN 1 ELSE 0 END,
                   page_start,
                   sort_order,
                   ctid""",
            (document_id,),
        ).fetchall()


def _fetch_tables(conn: Connection, document_id: str) -> list[dict]:
    """Fetch all document_table rows for a document."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """
            SELECT id, section_id, page, page_start, page_end, table_title, table_html, raw_json
            FROM document_table
            WHERE document_id = %s
            ORDER BY
                CASE WHEN page_start IS NULL THEN 1 ELSE 0 END,
                page_start,
                page
            """,
            (document_id,),
        ).fetchall()


def _fetch_document(conn: Connection, document_id: str) -> dict | None:
    """Fetch the document row, including persisted parse assets."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """
            SELECT id, parser_name, parser_version, raw_payload
            FROM document
            WHERE id = %s
            """,
            (document_id,),
        ).fetchone()


def _build_processing_scopes(
    sections: list[dict],
    tables: list[dict],
    *,
    document: dict | None = None,
    document_id: str | None = None,
) -> list[ProcessingScope]:
    """Build processing scopes from structured document assets."""
    parsed_document_id: UUID
    if document and document.get("id"):
        try:
            parsed_document_id = UUID(str(document["id"]))
        except (TypeError, ValueError):
            parsed_document_id = UUID(int=0)
    else:
        parsed_document_id = UUID(int=0)
    try:
        if document_id:
            parsed_document_id = UUID(document_id)
    except (TypeError, ValueError):
        pass

    asset = build_document_asset(
        document_id=parsed_document_id,
        document=document,
        sections=sections,
        tables=tables,
    )
    bounded_pages = [
        page_no
        for section in sections
        for page_no in (section.get("page_start"), section.get("page_end"))
        if isinstance(page_no, int) and page_no > 0
    ]
    if asset.pages and bounded_pages:
        first_page = min(bounded_pages)
        last_page = max(bounded_pages)
        filtered_pages = [
            page
            for page in asset.pages
            if isinstance(page.page_number, int) and first_page <= page.page_number <= last_page
        ]
        if filtered_pages:
            asset = replace(
                asset,
                pages=filtered_pages,
                full_markdown="\n\n".join(
                    str(page.normalized_text).strip()
                    for page in filtered_pages
                    if page.normalized_text
                ),
            )
    return build_structured_processing_scopes(asset)


def _build_block_processing_scopes(blocks: list[BlockSegment]) -> list[ProcessingScope]:
    scopes: list[ProcessingScope] = []
    for block in blocks:
        if block.segment_type == "commentary_block":
            scope_type = "commentary"
        elif block.segment_type == "table_requirement_block":
            scope_type = "table"
        else:
            scope_type = "normative"

        scopes.append(ProcessingScope(
            scope_type=scope_type,
            chapter_label=block.chapter_label,
            text=block.text,
            page_start=block.page_start or 0,
            page_end=block.page_end or block.page_start or 0,
            section_ids=list(block.section_ids),
            source_refs=list(block.source_refs),
            context={
                "block_segment_type": block.segment_type,
                "clause_no": block.clause_no,
                "table_title": block.table_title,
                "confidence": block.confidence,
            },
        ))
    return scopes


def _serialize_asset_tables_for_block_path(document_asset) -> list[dict]:
    serialized: list[dict] = []
    for table in document_asset.tables:
        table_id: str | None = None
        if table.source_ref.startswith("table:"):
            table_id = table.source_ref.split(":", 1)[1]
        serialized.append({
            "id": table_id,
            "page_start": table.page_start,
            "page_end": table.page_end,
            "table_title": table.table_title,
            "table_html": table.table_html,
            "raw_json": table.raw_json,
        })
    return serialized


def _resolved_block_clause_no(block: BlockSegment) -> str | None:
    candidates = [
        block.clause_no,
        block.chapter_label,
    ]
    if block.text:
        candidates.append(block.text.splitlines()[0])

    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        match = _BLOCK_CLAUSE_NO_RE.match(text)
        if match:
            return match.group(1)
    return None


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[dict[str, object]]] = []
        self._current_row: list[dict[str, object]] | None = None
        self._current_cell: dict[str, object] | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
            return
        if tag in {"td", "th"} and self._current_row is not None:
            attr_map = dict(attrs)
            self._current_cell = {
                "rowspan": int(attr_map.get("rowspan") or 1),
                "colspan": int(attr_map.get("colspan") or 1),
            }
            self._text_parts = []
            return
        if tag == "br" and self._current_cell is not None:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            text = " ".join(unescape("".join(self._text_parts)).split())
            self._current_cell["text"] = text
            self._current_row.append(self._current_cell)
            self._current_cell = None
            self._text_parts = []
            return
        if tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._text_parts.append(data)


def _expand_table_rows(table_html: str) -> list[list[str]]:
    parser = _TableHTMLParser()
    parser.feed(table_html)

    expanded_rows: list[list[str]] = []
    pending: dict[int, tuple[int, str]] = {}

    for row in parser.rows:
        expanded: list[str] = []
        col_index = 0

        def _consume_pending() -> None:
            nonlocal col_index
            while col_index in pending:
                remaining, text = pending[col_index]
                expanded.append(text)
                if remaining <= 1:
                    del pending[col_index]
                else:
                    pending[col_index] = (remaining - 1, text)
                col_index += 1

        _consume_pending()
        for cell in row:
            _consume_pending()
            text = str(cell.get("text") or "").strip()
            rowspan = max(1, int(cell.get("rowspan") or 1))
            colspan = max(1, int(cell.get("colspan") or 1))
            for _ in range(colspan):
                expanded.append(text)
                if rowspan > 1:
                    pending[col_index] = (rowspan - 1, text)
                col_index += 1
        _consume_pending()
        if any(value.strip() for value in expanded):
            expanded_rows.append(expanded)

    return expanded_rows


def _deterministic_table_entries_from_block(block: BlockSegment) -> list[dict]:
    table_html = str(block.table_html or "").strip()
    table_title = str(block.table_title or "").strip()
    if not table_html or not table_title:
        return []

    rows = _expand_table_rows(table_html)
    if len(rows) < 2:
        return []

    header = [cell.strip() for cell in rows[0]]
    width = max(len(header), *(len(row) for row in rows[1:]))
    if width < 2:
        return []
    header += [""] * (width - len(header))

    grouped_rows: dict[str, list[str]] = {}
    grouped_remarks: dict[str, list[str]] = {}

    for raw_row in rows[1:]:
        row = list(raw_row) + [""] * (width - len(raw_row))
        primary = row[0].strip()
        if not primary:
            continue

        row_parts: list[str] = []
        remark_parts = grouped_remarks.setdefault(primary, [])
        for index, cell in enumerate(row[1:], start=1):
            cell_text = cell.strip()
            if not cell_text or cell_text == "-":
                continue
            column_name = header[index].strip() or f"列{index + 1}"
            if column_name == "备注":
                if cell_text not in remark_parts:
                    remark_parts.append(cell_text)
                continue
            row_parts.append(f"{column_name}{cell_text}")

        if row_parts:
            grouped_rows.setdefault(primary, []).append("，".join(row_parts))

    entries: list[dict] = []
    for primary, row_parts in grouped_rows.items():
        sentence_parts = list(row_parts)
        remarks = grouped_remarks.get(primary, [])
        if remarks:
            sentence_parts.append(f"备注：{'；'.join(remarks)}")
        clause_text = f"{primary}：" + "；".join(sentence_parts) + "。"
        entries.append({
            "clause_no": None,
            "clause_title": table_title,
            "clause_text": clause_text,
            "summary": None,
            "tags": [],
            "page_start": block.page_start,
            "page_end": block.page_end,
            "clause_type": "normative",
            "source_type": "table",
            "source_ref": block.source_refs[0] if block.source_refs else None,
            "source_refs": list(block.source_refs),
            "source_label": block.chapter_label,
        })

    return entries


def _should_extract_normative_block_deterministically(clause_no: str, text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if clause_no.startswith("2.0."):
        return True
    if len(normalized) > 140:
        return False
    if _DETERMINISTIC_LIST_SIGNAL_RE.search(normalized):
        return False
    if normalized.endswith("："):
        return False
    return True


def _deterministic_entries_from_block(block: BlockSegment) -> list[dict]:
    if block.segment_type == "table_requirement_block":
        return _deterministic_table_entries_from_block(block)
    text = block.text.strip()
    if not text:
        return []
    clause_no = _resolved_block_clause_no(block)

    if block.segment_type == "commentary_block":
        clause_type = "commentary"
    else:
        if block.segment_type not in {"normative_clause_block", "appendix_block"}:
            return []
        if not clause_no:
            return []
        if not _should_extract_normative_block_deterministically(clause_no, text):
            return []
        clause_type = "normative"

    return [{
        "clause_no": clause_no,
        "clause_title": None,
        "clause_text": text,
        "summary": None,
        "tags": [],
        "page_start": block.page_start,
        "page_end": block.page_end,
        "clause_type": clause_type,
        "source_type": "text",
        "source_ref": block.source_refs[0] if block.source_refs else None,
        "source_refs": list(block.source_refs),
        "source_label": block.chapter_label,
    }]


def _deterministic_entries_from_scope(scope: ProcessingScope) -> list[dict]:
    if scope.scope_type != "table":
        return []
    table_title = ""
    if isinstance(scope.context, dict):
        table_title = str(scope.context.get("table_title") or "").strip()
    block = BlockSegment(
        segment_type="table_requirement_block",
        chapter_label=scope.chapter_label,
        text=scope.text,
        page_start=scope.page_start,
        page_end=scope.page_end,
        table_title=table_title or None,
        table_html=scope.text,
        source_refs=list(scope.source_refs),
        confidence="high",
    )
    return _deterministic_table_entries_from_block(block)


def _should_skip_block_for_ai(block: BlockSegment) -> bool:
    if block.segment_type in {"heading_only_block", "non_clause_block"}:
        return True
    if block.segment_type in {"commentary_block", "appendix_block"} and not block.text.strip():
        return True
    if block.segment_type != "table_requirement_block" and _resolved_block_clause_no(block) is None:
        return True
    return False


_ACTUAL_CHAPTER_TITLE = re.compile(r"^\d{1,2}\s+\S")
_ACTUAL_CLAUSE_TITLE = re.compile(r"^\d+(?:\.\d+)+\s+\S")
_TOC_PAGE_REF = re.compile(r"(?:\(\d+\)|（\d+）)\s*$")
_TOC_DOT_LEADERS = re.compile(r"[.…]{2,}")
_BLOCK_CLAUSE_NO_RE = re.compile(r"^\s*((?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)+))\b")
_DETERMINISTIC_LIST_SIGNAL_RE = re.compile(r"(?:下列|如下|；|\n\s*[（(]?\d+[)）]|[一二三四五六七八九十]+、)")
_CLAUSE_LIKE_SECTION_CODE = re.compile(r"^(?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)*)$")
_NUMERIC_SECTION_CODE = re.compile(r"^\d+(?:\.\d+)*$")
_SECTION_TITLE_SENTENCE_SIGNAL_RE = re.compile(r"[，。；：]|应|不得|必须|严禁|禁止|宜|可")


def _section_heading_text(section: dict) -> str:
    code = str(section.get("section_code") or "").strip()
    title = str(section.get("title") or "").strip()
    return f"{code} {title}".strip()


def _is_clause_like_section_code(code: str) -> bool:
    return bool(code and _CLAUSE_LIKE_SECTION_CODE.match(code) and code.count(".") >= 2)


def _section_title_carries_clause_text(section: dict) -> bool:
    code = str(section.get("section_code") or "").strip()
    if not _is_clause_like_section_code(code):
        return False
    title = str(section.get("title") or "").strip()
    if not title or _TOC_PAGE_REF.search(title) or _TOC_DOT_LEADERS.search(title):
        return False
    if str(section.get("text") or "").strip():
        return False
    return bool(_SECTION_TITLE_SENTENCE_SIGNAL_RE.search(title))


def _coerce_inline_clause_text(section: dict) -> dict:
    if not _section_title_carries_clause_text(section):
        return dict(section)
    normalized = dict(section)
    normalized["text"] = str(section.get("title") or "").strip()
    return normalized


def _should_seed_section_title_as_clause(section: dict) -> bool:
    code = str(section.get("section_code") or "").strip()
    if not _is_clause_like_section_code(code):
        return False
    title = str(section.get("title") or "").strip()
    if not title or _TOC_PAGE_REF.search(title) or _TOC_DOT_LEADERS.search(title):
        return False
    if str(section.get("text") or "").strip():
        return False
    return bool(_SECTION_TITLE_SENTENCE_SIGNAL_RE.search(title))


def _seed_section_title_entries(sections: list[dict]) -> list[dict]:
    seeded_entries: list[dict] = []
    seen_clause_nos: set[str] = set()

    for section in sections:
        if not _should_seed_section_title_as_clause(section):
            continue
        clause_no = str(section.get("section_code") or "").strip()
        if clause_no in seen_clause_nos:
            continue
        seen_clause_nos.add(clause_no)
        section_id = str(section.get("id") or "").strip()
        source_ref = f"document_section:{section_id}" if section_id else None
        seeded_entries.append({
            "clause_no": clause_no,
            "clause_title": None,
            "clause_text": str(section.get("title") or "").strip(),
            "summary": None,
            "tags": [],
            "page_start": section.get("page_start"),
            "page_end": section.get("page_end"),
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": source_ref,
            "source_refs": [source_ref] if source_ref else [],
            "source_label": _section_heading_text(section),
        })

    return seeded_entries


def _is_heading_only_outline_text(clause_no: str, clause_text: str) -> bool:
    normalized_text = " ".join(str(clause_text or "").split())
    if not normalized_text:
        return True
    if normalized_text == clause_no:
        return True
    remainder = normalized_text
    if clause_no:
        prefix = f"{clause_no} "
        if normalized_text.startswith(prefix):
            remainder = normalized_text[len(prefix):].strip()
    if not remainder:
        return True
    return not bool(_SECTION_TITLE_SENTENCE_SIGNAL_RE.search(remainder))


def _prune_empty_outline_hosts(
    clauses: list[dict],
    *,
    outline_clause_nos: set[str] | None = None,
) -> list[dict]:
    if not clauses or not outline_clause_nos:
        return clauses

    children_by_parent: dict[UUID, list[dict]] = {}
    for clause in clauses:
        parent_id = clause.get("parent_id")
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(clause)

    removed_parent_ids: dict[UUID, UUID | None] = {}
    kept: list[dict] = []
    for clause in clauses:
        clause_id = clause.get("id")
        clause_no = str(clause.get("clause_no") or "").strip()
        child_clauses = [
            child
            for child in children_by_parent.get(clause_id, [])
            if child.get("node_type", "clause") == "clause"
        ]
        should_drop = (
            clause.get("clause_type") == "normative"
            and clause.get("node_type", "clause") == "clause"
            and clause.get("source_type", "text") == "text"
            and clause_no in outline_clause_nos
            and "." in clause_no
            and _is_heading_only_outline_text(clause_no, str(clause.get("clause_text") or ""))
            and bool(child_clauses)
        )
        if should_drop:
            removed_parent_ids[clause_id] = clause.get("parent_id")
            continue
        kept.append(clause)

    if not removed_parent_ids:
        return clauses

    for clause in kept:
        parent_id = clause.get("parent_id")
        while parent_id in removed_parent_ids:
            parent_id = removed_parent_ids[parent_id]
        clause["parent_id"] = parent_id

    return kept


def _is_toc_heading(section: dict) -> bool:
    title = _section_heading_text(section)
    if _TOC_PAGE_REF.search(title):
        return True
    if _TOC_DOT_LEADERS.search(title):
        return True
    text = (section.get("text") or "").strip()
    if text:
        return False
    return False


def _normalize_sections_for_processing(sections: list[dict]) -> list[dict]:
    """Trim front matter and drop empty TOC headings before clause extraction."""
    if not sections:
        return []

    start_idx = 0
    for idx, section in enumerate(sections):
        heading = _section_heading_text(section)
        if _is_toc_heading(section):
            continue
        if _ACTUAL_CHAPTER_TITLE.match(heading) or _ACTUAL_CLAUSE_TITLE.match(heading):
            start_idx = idx
            break

    normalized = [
        _coerce_inline_clause_text(section)
        for section in sections[start_idx:]
        if not _is_toc_heading(section)
    ]

    logger.info(
        "sections_normalized",
        original_count=len(sections),
        normalized_count=len(normalized),
        first_title=(normalized[0].get("title") if normalized else None),
    )
    return normalized


def _collect_outline_clause_nos(sections: list[dict]) -> set[str]:
    codes: set[str] = set()
    for section in sections:
        raw_code = section.get("section_code")
        if raw_code is None:
            continue
        code = str(raw_code).strip()
        if not code or not _NUMERIC_SECTION_CODE.match(code):
            continue
        codes.add(code)
    return codes


def _call_ai_gateway(
    conn: Connection,
    prompt: str,
    scope_label: str,
) -> str:
    """Call AI Gateway with tag_clauses agent config credentials."""
    config = _agent_repo.get_by_key(conn, "tag_clauses")
    if not config or not config.enabled:
        raise RuntimeError("Agent config 'tag_clauses' not found or disabled")

    payload: dict = {
        "task_type": "tag_clauses",
        "messages": [
            {"role": "system", "content": "你是一个专业的建筑工程规范条款提取助手。仅输出JSON，不要输出其他内容。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }

    # Apply per-agent credentials as overrides
    if config.base_url and config.api_key:
        payload["primary_override"] = {
            "base_url": config.base_url,
            "api_key": config.api_key,
            "model": config.primary_model or "deepseek-chat",
        }
    if config.fallback_base_url and config.fallback_api_key:
        payload["fallback_override"] = {
            "base_url": config.fallback_base_url,
            "api_key": config.fallback_api_key,
            "model": config.fallback_model or "qwen-plus",
        }

    url = _ai_gateway_chat_url(AI_GATEWAY_URL)
    timeout = _ai_gateway_timeout_seconds(config.primary_model)
    resp = httpx.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    content = data.get("content", "")
    logger.info(
        "ai_gateway_response",
        scope=scope_label,
        model=data.get("resolved_model"),
        input_tokens=data.get("input_tokens", 0),
        output_tokens=data.get("output_tokens", 0),
        used_fallback=data.get("used_fallback", False),
    )
    return content


def _parse_llm_json(raw: str) -> list[dict]:
    """Extract JSON array from LLM response, handling markdown fences."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for target in ("[", "{"):
            for index, char in enumerate(text):
                if char != target:
                    continue
                try:
                    result, _end = decoder.raw_decode(text[index:])
                    if isinstance(result, list):
                        return result
                    if isinstance(result, dict):
                        return [result]
                except json.JSONDecodeError:
                    continue
    logger.warning("llm_json_parse_failed", raw_length=len(raw))
    return []


def _is_retryable_ai_gateway_status(exc: httpx.HTTPStatusError) -> bool:
    response = exc.response
    return response.status_code in {502, 504}


def _process_scope_with_retries(
    conn: Connection,
    scope: ProcessingScope,
) -> list[dict]:
    """Process one scope and split it into smaller chunks when the provider times out."""
    pending_scopes: list[tuple[ProcessingScope, int]] = [(scope, 0)]
    all_entries: list[dict] = []

    while pending_scopes:
        current_scope, attempt = pending_scopes.pop(0)
        prompt = build_prompt(current_scope)
        try:
            raw_response = _call_ai_gateway(conn, prompt, current_scope.chapter_label)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and not _is_retryable_ai_gateway_status(exc):
                raise
            if attempt < _MAX_SCOPE_RETRY_ATTEMPTS:
                logger.warning(
                    "scope_retrying",
                    scope=current_scope.chapter_label,
                    attempt=attempt + 1,
                    max_attempts=_MAX_SCOPE_RETRY_ATTEMPTS,
                )
                pending_scopes = [(current_scope, attempt + 1)] + pending_scopes
                continue
            retry_scopes = rebalance_scopes(
                [current_scope],
                max_chars=max(500, len(current_scope.text) // 2),
                max_clause_blocks=2,
            )
            if len(retry_scopes) <= 1:
                raise

            logger.warning(
                "scope_timeout_rebalanced",
                scope=current_scope.chapter_label,
                retry_scopes=[s.chapter_label for s in retry_scopes],
            )
            pending_scopes = [(retry_scope, 0) for retry_scope in retry_scopes] + pending_scopes
            continue

        entries = _parse_llm_json(raw_response)
        for entry in entries:
            _apply_scope_defaults(entry, current_scope)
        all_entries.extend(entries)

    return all_entries


def _apply_scope_defaults(entry: dict, scope: ProcessingScope) -> None:
    """Recursively backfill missing provenance and page anchors from the scope."""
    scope_refs = [ref for ref in scope.source_refs if isinstance(ref, str) and ref.strip()]
    clause_type = "commentary" if scope.scope_type == "commentary" else "normative"
    source_type = "table" if scope.scope_type == "table" else "text"
    scope_page_start = scope.page_start if isinstance(scope.page_start, int) and scope.page_start > 0 else None
    scope_page_end = scope.page_end if isinstance(scope.page_end, int) and scope.page_end > 0 else None

    if not entry.get("clause_type"):
        entry["clause_type"] = clause_type
    entry_page_start = entry.get("page_start")
    entry_page_end = entry.get("page_end")
    page_start_in_scope = (
        isinstance(entry_page_start, int)
        and entry_page_start > 0
        and (scope_page_start is None or entry_page_start >= scope_page_start)
        and (scope_page_end is None or entry_page_start <= scope_page_end)
    )
    page_end_in_scope = (
        isinstance(entry_page_end, int)
        and entry_page_end > 0
        and (scope_page_start is None or entry_page_end >= scope_page_start)
        and (scope_page_end is None or entry_page_end <= scope_page_end)
    )
    if not page_start_in_scope or not page_end_in_scope:
        entry["page_start"] = scope_page_start
        entry["page_end"] = scope_page_end
    if not entry.get("source_ref") and scope_refs:
        entry["source_ref"] = scope_refs[0]
    if not entry.get("source_refs") and scope_refs:
        entry["source_refs"] = list(scope_refs)
    if not entry.get("source_type"):
        entry["source_type"] = source_type
    if not entry.get("source_label"):
        entry["source_label"] = scope.chapter_label

    children = entry.get("children")
    if not isinstance(children, list):
        return
    for child in children:
        if isinstance(child, dict):
            _apply_scope_defaults(child, scope)


def ensure_standard_ocr(
    conn: Connection,
    *,
    document_id: str,
) -> int:
    """Ensure OCR sections exist for a standard document."""
    sections = _fetch_sections(conn, document_id)
    if sections:
        return len(sections)

    logger.info("no_sections_found_triggering_mineru", document_id=document_id)
    count = _parse_via_mineru(conn, document_id)
    logger.info("mineru_parsing_complete", section_count=count)

    sections = _fetch_sections(conn, document_id)
    if not sections:
        raise ValueError(
            f"MinerU returned 0 parseable sections for document {document_id}"
        )
    return len(sections)


def process_standard_ai(
    conn: Connection,
    *,
    standard_id: UUID,
    document_id: str,
) -> dict:
    """Run the AI extraction phase using existing OCR sections."""
    started_at = time.time()

    try:
        raw_sections = _fetch_sections(conn, document_id)
        if not raw_sections:
            raise ValueError(f"No OCR sections available for document {document_id}")
        tables = _fetch_tables(conn, document_id)
        document = _fetch_document(conn, document_id)
        document_asset = build_document_asset(
            document_id=UUID(document_id),
            document=document,
            sections=raw_sections,
            tables=tables,
        )
        sections = _normalize_sections_for_processing(raw_sections)
        if not sections:
            raise ValueError("No normalized sections available for processing")
        outline_clause_nos = (
            collect_outline_clause_nos_from_pages(document_asset.pages)
            | _collect_outline_clause_nos(raw_sections)
        )
        if standard_id in _SINGLE_STANDARD_BLOCK_EXPERIMENT_IDS:
            logger.info("single_standard_block_path_enabled", standard_id=str(standard_id))
            blocks = build_single_standard_blocks(sections, tables)
            block_type_counts: dict[str, int] = {}
            for block in blocks:
                block_type_counts[block.segment_type] = block_type_counts.get(block.segment_type, 0) + 1
            logger.info("single_standard_blocks_built", counts=block_type_counts)

            deterministic_entries = []
            scopes = _build_block_processing_scopes(blocks)
        else:
            blocks = []
            deterministic_entries = []
            scopes = _build_processing_scopes(
                sections,
                tables,
                document=document,
                document_id=document_id,
            )
            scopes = rebalance_scopes(scopes)
        if not scopes and not deterministic_entries:
            raise ValueError("No processing scopes generated")

        all_entries: list[dict] = list(deterministic_entries)
        for i, scope in enumerate(scopes):
            current_block = blocks[i] if standard_id in _SINGLE_STANDARD_BLOCK_EXPERIMENT_IDS else None
            if current_block is not None and _should_skip_block_for_ai(current_block):
                logger.info(
                    "processing_scope_skipped",
                    index=i + 1,
                    total=len(scopes),
                    chapter=scope.chapter_label,
                    scope_type=scope.scope_type,
                    reason=current_block.segment_type,
                )
                continue

            direct_entries = (
                _deterministic_entries_from_block(current_block)
                if current_block is not None
                else _deterministic_entries_from_scope(scope)
            )
            if direct_entries:
                all_entries.extend(direct_entries)
                logger.info(
                    "processing_scope_deterministic",
                    index=i + 1,
                    total=len(scopes),
                    scope_type=scope.scope_type,
                    chapter=scope.chapter_label,
                    entry_count=len(direct_entries),
                )
                continue
            logger.info(
                "processing_scope",
                index=i + 1,
                total=len(scopes),
                scope_type=scope.scope_type,
                chapter=scope.chapter_label,
            )

            entries = _process_scope_with_retries(conn, scope)
            all_entries.extend(entries)

            if i < len(scopes) - 1:
                delay_seconds = _scope_delay_seconds()
                if delay_seconds > 0:
                    time.sleep(delay_seconds)

        if standard_id in _SINGLE_STANDARD_BLOCK_EXPERIMENT_IDS:
            all_entries.extend(_seed_section_title_entries(sections))

        logger.info("all_scopes_processed", total_entries=len(all_entries))

        clauses = build_tree(all_entries, standard_id)
        clauses = _prune_empty_outline_hosts(clauses, outline_clause_nos=outline_clause_nos)
        clauses = link_commentary(clauses)
        structured_validation = validate_clauses(clauses, outline_clause_nos=outline_clause_nos)
        repair_tasks = build_repair_tasks(clauses, structured_validation.issues)
        repair_patches: list = []
        repair_error: str | None = None
        if repair_tasks:
            try:
                repair_patches = run_repair_tasks(conn=conn, document_id=document_id, tasks=repair_tasks)
            except Exception as exc:
                repair_error = str(exc)
                logger.warning(
                    "repair_tasks_failed",
                    standard_id=str(standard_id),
                    document_id=document_id,
                    task_count=len(repair_tasks),
                    error=repair_error,
                )
        clauses = merge_repair_patches(clauses, repair_patches)
        revalidated = validate_clauses(clauses, outline_clause_nos=outline_clause_nos)
        warnings = validate_tree(clauses)
        if repair_error:
            warnings.append(f"repair tasks failed: {repair_error}")
        combined_warnings = warnings + revalidated.warning_messages(limit=10)

        _std_repo.delete_clauses(conn, standard_id)
        inserted = _std_repo.bulk_create_clauses(conn, clauses)

        standard = _std_repo.get_standard(conn, standard_id)
        _index_clauses(standard, clauses)

        elapsed = time.time() - started_at
        return {
            "standard_id": str(standard_id),
            "status": "completed",
            "total_clauses": inserted,
            "normative": sum(1 for c in clauses if c["clause_type"] == "normative"),
            "commentary": sum(1 for c in clauses if c["clause_type"] == "commentary"),
            "scopes_processed": len(scopes),
            "repair_task_count": len(repair_tasks),
            "issues_before_repair": len(structured_validation.issues),
            "issues_after_repair": len(revalidated.issues),
            "repair_error": repair_error,
            "warnings": combined_warnings[:5],
            "validation": revalidated.to_dict(),
            "elapsed_seconds": round(elapsed, 1),
        }

    except Exception as exc:
        logger.exception("processing_failed", standard_id=str(standard_id), error=str(exc))
        raise


def process_standard(
    conn: Connection,
    standard_id: UUID,
    document_id: str,
) -> dict:
    """Backward-compatible wrapper for the full OCR + AI pipeline."""
    _std_repo.update_processing_status(conn, standard_id, "parsing")
    try:
        ensure_standard_ocr(conn, document_id=document_id)
        _std_repo.update_processing_status(conn, standard_id, "processing")
        summary = process_standard_ai(conn, standard_id=standard_id, document_id=document_id)
        _std_repo.update_processing_status(conn, standard_id, "completed")
        logger.info("processing_completed", **summary)
        return summary
    except Exception as exc:
        logger.exception("processing_failed", standard_id=str(standard_id), error=str(exc))
        _std_repo.update_processing_status(conn, standard_id, "failed", error_message=str(exc))
        return {
            "standard_id": str(standard_id),
            "status": "failed",
            "error": str(exc),
        }


def _index_clauses(standard: dict | None, clauses: list[dict]) -> None:
    """Index clauses to OpenSearch (best-effort, doesn't fail the pipeline)."""
    if not standard or not clauses:
        return

    try:
        manager = IndexManager()
        docs = build_clause_index_docs(standard, clauses)
        asyncio.run(manager.bulk_index("clause_index", docs))
    except Exception:
        logger.warning("opensearch_indexing_failed", exc_info=True)
