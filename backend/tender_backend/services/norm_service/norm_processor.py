"""Orchestrator: MinerU parse → compress → split → per-scope AI → merge → validate → persist + index.

This is the core processing pipeline for standard PDFs.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import os
import random
import re
import time
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
from tender_backend.db.repositories.skill_definition_repo import SkillDefinitionRepository
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.block_segments import BlockSegment, build_single_standard_blocks
from tender_backend.services.norm_service.document_assets import build_document_asset
from tender_backend.services.norm_service.outline_rebuilder import collect_outline_clause_nos_from_pages
from tender_backend.services.norm_service.parse_profiles import CN_GB_PROFILE, ParseProfile
from tender_backend.services.norm_service.parse_artifacts import (
    AiResponseArtifact,
    serialize_ai_response_artifacts,
)
from tender_backend.services.norm_service.profile_resolver import resolve_standard_profile
from tender_backend.services.norm_service.quality_report import build_standard_quality_report
from tender_backend.services.norm_service.repair_tasks import build_repair_tasks
from tender_backend.services.norm_service.section_cleaning import clean_sections
from tender_backend.services.norm_service.skill_plugins import (
    ExecutedParseSkill,
    ParseSkillContext,
    default_parse_skill_plugins,
    run_parse_skill_hooks,
)
from tender_backend.services.norm_service.table_requirements import (
    deterministic_table_entries_from_block as build_table_requirement_entries,
)
from tender_backend.services.norm_service.ast_merger import merge_repair_patches
from tender_backend.services.norm_service.prompt_builder import build_prompt
from tender_backend.services.norm_service.scope_splitter import ProcessingScope, rebalance_scopes
from tender_backend.services.norm_service.structural_nodes import build_processing_scopes as build_structured_processing_scopes
from tender_backend.services.norm_service.tree_builder import build_tree, link_commentary, validate_tree
from tender_backend.services.norm_service.validation import validate_clauses
from tender_backend.services.parse_service.mineru_client import build_mineru_auth_headers
from tender_backend.services.parse_service.mineru_normalizer import normalize_mineru_payload
from tender_backend.services.search_service.index_manager import IndexManager
from tender_backend.services.storage_service.project_file_storage import ProjectFileStorage
from tender_backend.services.vision_service.repair_service import run_repair_tasks
from tender_backend.tools.reindex_standard_clauses import build_clause_index_docs

logger = structlog.stdlib.get_logger(__name__)

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:8001")
_MAX_SCOPE_RETRY_ATTEMPTS = 2

_std_repo = StandardRepository()
_agent_repo = AgentConfigRepository()
_skill_repo = SkillDefinitionRepository()
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


def _should_use_single_standard_block_path(
    profile: ParseProfile,
    sections: list[dict] | None = None,
) -> bool:
    if not profile.deterministic_block_parser:
        return False
    if sections is None:
        return True
    return any(str(section.get("section_code") or "").strip() for section in sections)


def _build_profile_blocks(
    sections: list[dict],
    tables: list[dict],
    *,
    profile: ParseProfile,
) -> list[BlockSegment]:
    if profile == CN_GB_PROFILE:
        return build_single_standard_blocks(sections, tables)
    return build_single_standard_blocks(sections, tables, profile=profile)


def _parse_skill_plugins():
    return default_parse_skill_plugins()


def _active_parse_skill_names(conn: Connection) -> set[str]:
    try:
        return {
            row.skill_name
            for row in _skill_repo.list_all(conn)
            if row.active
        }
    except Exception as exc:
        logger.warning("parse_skill_lookup_failed", error=str(exc))
        return set()


def _serialize_executed_skills(executed_skills: list[ExecutedParseSkill]) -> list[dict]:
    return [asdict(skill) for skill in executed_skills]


def _has_blocking_skill_failure(executed_skills: list[ExecutedParseSkill]) -> bool:
    return any(skill.blocking for skill in executed_skills)


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


def _extract_middle_json_from_zip(content: bytes) -> dict | None:
    """Read the `*_middle.json` structured payload from a MinerU result zip.

    Returns None if the zip does not carry a middle.json (legacy / failure).
    Prefers filenames ending in `_middle.json`; falls back to any JSON whose
    top-level object contains a `pdf_info` array.
    """
    with ZipFile(BytesIO(content)) as zf:
        names = zf.namelist()
        candidates = [name for name in names if name.endswith("_middle.json")]
        if not candidates:
            candidates = [name for name in names if name.endswith(".json")]

        for name in candidates:
            try:
                payload = json.loads(zf.read(name).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and isinstance(payload.get("pdf_info"), list):
                return payload
    return None


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
        if not isinstance(page, int):
            page = table.get("page_start")
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
    headers = build_mineru_auth_headers(config.api_key)
    settings = get_settings()

    # Step 1: Ask MinerU for a batch upload URL.
    logger.info("mineru_requesting_upload_url", document_id=document_id, url=api_root)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    request_payload: dict[str, object] = {
        "files": [{
            "name": os.path.basename(pdf_path),
            "data_id": document_id,
            "is_ocr": getattr(settings, "standard_mineru_is_ocr", True),
        }],
        "model_version": getattr(settings, "standard_mineru_model_version", "vlm"),
        "language": getattr(settings, "standard_mineru_language", "ch"),
        "enable_table": getattr(settings, "standard_mineru_enable_table", True),
        "enable_formula": getattr(settings, "standard_mineru_enable_formula", False),
    }
    page_ranges = getattr(settings, "standard_mineru_page_ranges", None)
    if page_ranges:
        request_payload["files"][0]["page_ranges"] = page_ranges
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
            middle_json = _extract_middle_json_from_zip(zip_resp.content)
            if middle_json is None:
                raise RuntimeError(
                    "MinerU result zip does not contain a *_middle.json payload; "
                    "the normalizer requires the canonical pdf_info structure."
                )

            middle_json.setdefault("full_markdown", raw_content)
            normalized = normalize_mineru_payload(middle_json)
            pages = normalized["pages"]
            tables = normalized["tables"]
            full_markdown = normalized["full_markdown"]

            sections = _mineru_to_sections(full_markdown, pages)
            update_document_parse_assets(
                conn,
                document_id=UUID(document_id),
                parser_name="mineru",
                parser_version=normalized.get("parser_version"),
                raw_payload={
                    "parser_version": normalized.get("parser_version"),
                    "pages": pages,
                    "tables": tables,
                    "full_markdown": full_markdown,
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
                   CASE WHEN sort_order IS NULL THEN 1 ELSE 0 END,
                   sort_order,
                   CASE WHEN page_start IS NULL THEN 1 ELSE 0 END,
                   page_start,
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
    first_content_section = next(
        (
            section
            for section in sections
            if str(section.get("title") or "").strip() or str(section.get("text") or "").strip()
        ),
        None,
    )
    should_trim_pages_by_section_bounds = bool(
        first_content_section
        and isinstance(first_content_section.get("page_start"), int)
        and first_content_section.get("page_start") > 0
    )
    bounded_pages = [
        page_no
        for section in sections
        for page_no in (section.get("page_start"), section.get("page_end"))
        if isinstance(page_no, int) and page_no > 0
    ]
    if asset.pages and bounded_pages and should_trim_pages_by_section_bounds:
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


def _deterministic_table_entries_from_block(
    block: BlockSegment,
    *,
    strategy: str | None = None,
) -> list[dict]:
    return build_table_requirement_entries(block, strategy=strategy)


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
        compact_text = re.sub(r"\s+", "", normalized)
        compact_clause_no = re.sub(r"\s+", "", clause_no)
        return bool(compact_clause_no and f"表{compact_clause_no}" in compact_text)
    return True


def _deterministic_entries_from_block(
    block: BlockSegment,
    *,
    table_strategy: str | None = None,
) -> list[dict]:
    if block.segment_type == "table_requirement_block":
        return _deterministic_table_entries_from_block(block, strategy=table_strategy)
    text = block.text.strip()
    if not text:
        return []
    page_start = block.page_start
    page_end = block.page_end if block.page_end is not None else block.page_start
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
        "page_start": page_start,
        "page_end": page_end,
        "clause_type": clause_type,
        "source_type": "text",
        "source_ref": block.source_refs[0] if block.source_refs else None,
        "source_refs": list(block.source_refs),
        "source_label": block.chapter_label,
    }]


def _deterministic_entries_from_scope(
    scope: ProcessingScope,
    *,
    table_strategy: str | None = None,
) -> list[dict]:
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
    return _deterministic_table_entries_from_block(block, strategy=table_strategy)


def _canonical_scope_source_label(label: object) -> str:
    return _SCOPE_LABEL_SPLIT_SUFFIX_RE.sub("", str(label or "").strip())


def _host_entry_from_scope_label(
    scope: ProcessingScope,
    *,
    first_clause_no: str,
    source_ref: str | None,
    source_label: str,
) -> dict | None:
    normalized_label = source_label
    if not normalized_label:
        return None

    appendix_match = _INLINE_SCOPE_APPENDIX_LABEL_RE.match(normalized_label)
    if appendix_match:
        clause_no = str(appendix_match.group(1) or "").strip()
        clause_title = str(appendix_match.group(2) or "").strip()
        if clause_no and clause_title and first_clause_no.startswith(f"{clause_no}."):
            return {
                "clause_no": clause_no,
                "clause_title": clause_title,
                "clause_text": f"附录{clause_no}{clause_title}",
                "summary": None,
                "tags": [],
                "page_start": scope.page_start,
                "page_end": scope.page_end,
                "clause_type": "normative",
                "source_type": "text",
                "source_ref": source_ref,
                "source_refs": list(scope.source_refs),
                "source_label": source_label,
            }

    host_match = _INLINE_SCOPE_HOST_LABEL_RE.match(normalized_label)
    if not host_match:
        first_line = str(scope.text or "").splitlines()[0].strip() if str(scope.text or "").strip() else ""
        host_match = _INLINE_SCOPE_HOST_LABEL_RE.match(first_line)
    if not host_match:
        return None

    clause_no = str(host_match.group(1) or "").strip()
    clause_title = str(host_match.group(2) or "").strip()
    if not clause_no or not clause_title:
        return None
    if clause_no == first_clause_no or not first_clause_no.startswith(f"{clause_no}."):
        return None

    return {
        "clause_no": clause_no,
        "clause_title": clause_title,
        "clause_text": f"{clause_no}{clause_title}",
        "summary": None,
        "tags": [],
        "page_start": scope.page_start,
        "page_end": scope.page_end,
        "clause_type": "normative",
        "source_type": "text",
        "source_ref": source_ref,
        "source_refs": list(scope.source_refs),
        "source_label": source_label,
    }


def _scope_host_clause_no(scope: ProcessingScope) -> str | None:
    source_label = _canonical_scope_source_label(scope.chapter_label)
    appendix_match = _INLINE_SCOPE_APPENDIX_LABEL_RE.match(source_label)
    if appendix_match:
        clause_no = str(appendix_match.group(1) or "").strip()
        return clause_no or None

    host_match = _INLINE_SCOPE_HOST_LABEL_RE.match(source_label)
    if not host_match:
        return None
    clause_no = str(host_match.group(1) or "").strip()
    return clause_no or None


def _clause_no_belongs_to_scope(clause_no: str, scope: ProcessingScope) -> bool:
    expected_host = _scope_host_clause_no(scope)
    if not expected_host:
        return True
    return clause_no == expected_host or clause_no.startswith(f"{expected_host}.")


def _collect_known_clause_nos(sections: list[dict]) -> set[str]:
    known: set[str] = set()
    for section in sections:
        for candidate in (
            str(section.get("section_code") or "").strip(),
            _section_host_code(section),
        ):
            if candidate and _STRUCTURED_CLAUSE_NO_RE.match(candidate):
                known.add(candidate)
    return known


def _effective_scope_clause_allowlist(
    scope: ProcessingScope,
    allowed_clause_nos: set[str] | None,
) -> set[str] | None:
    if allowed_clause_nos is None:
        return None
    scope_host = _scope_host_clause_no(scope)
    scoped = {
        clause_no
        for clause_no in allowed_clause_nos
        if _clause_no_belongs_to_scope(clause_no, scope)
    }
    if not scoped:
        return None
    detailed = {
        clause_no
        for clause_no in scoped
        if scope_host is None or clause_no != scope_host
    }
    return scoped if detailed else None


def _sanitize_scope_entries(
    scope: ProcessingScope,
    entries: list[dict],
    *,
    allowed_clause_nos: set[str] | None = None,
) -> list[dict]:
    sanitized: list[dict] = []
    effective_allowed_clause_nos = _effective_scope_clause_allowlist(scope, allowed_clause_nos)

    def _sanitize_entry(entry: dict) -> dict | None:
        current = dict(entry)
        raw_clause_no = str(current.get("clause_no") or "").strip()
        node_type = str(current.get("node_type") or "").strip()

        if raw_clause_no and _STRUCTURED_CLAUSE_NO_RE.match(raw_clause_no):
            clause_allowed = _clause_no_belongs_to_scope(raw_clause_no, scope)
            if clause_allowed and effective_allowed_clause_nos is not None:
                clause_allowed = raw_clause_no in effective_allowed_clause_nos
            if not clause_allowed:
                if node_type in {"item", "subitem"}:
                    current.pop("clause_no", None)
                else:
                    return None

        children = current.get("children")
        if isinstance(children, list):
            current["children"] = [
                child
                for item in children
                if isinstance(item, dict)
                for child in [_sanitize_entry(item)]
                if child is not None
            ]
        return current

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sanitized_entry = _sanitize_entry(entry)
        if sanitized_entry is not None:
            sanitized.append(sanitized_entry)
    return sanitized


def _deterministic_inline_clause_entries_from_scope(
    scope: ProcessingScope,
    *,
    allowed_clause_nos: set[str] | None = None,
) -> list[dict]:
    if scope.scope_type != "normative":
        return []

    lines = [line.strip() for line in str(scope.text or "").splitlines() if line.strip()]
    if len(lines) < 2:
        return []

    clause_starts = [
        index
        for index, line in enumerate(lines)
        if _INLINE_SCOPE_CLAUSE_LINE_RE.match(line)
    ]
    if len(clause_starts) < 2:
        return []

    entries: list[dict] = []
    effective_allowed_clause_nos = _effective_scope_clause_allowlist(scope, allowed_clause_nos)
    source_ref = scope.source_refs[0] if scope.source_refs else None
    source_label = _canonical_scope_source_label(scope.chapter_label)
    first_clause_match = _INLINE_SCOPE_CLAUSE_LINE_RE.match(lines[clause_starts[0]])
    first_clause_no = str(first_clause_match.group(1) or "").strip() if first_clause_match else ""
    host_entry = _host_entry_from_scope_label(
        scope,
        first_clause_no=first_clause_no,
        source_ref=source_ref,
        source_label=source_label,
    )
    if host_entry is not None:
        entries.append(host_entry)

    for offset, start_index in enumerate(clause_starts):
        next_index = clause_starts[offset + 1] if offset + 1 < len(clause_starts) else len(lines)
        match = _INLINE_SCOPE_CLAUSE_LINE_RE.match(lines[start_index])
        if not match:
            continue
        clause_no = str(match.group(1) or "").strip()
        first_body = str(match.group(2) or "").strip()
        if not _clause_no_belongs_to_scope(clause_no, scope):
            continue
        if effective_allowed_clause_nos is not None and clause_no not in effective_allowed_clause_nos:
            continue
        body_lines = [first_body] if first_body else []
        body_lines.extend(lines[start_index + 1:next_index])
        clause_text = "\n".join(line for line in body_lines if line).strip()
        if not clause_no or not clause_text:
            continue
        entries.append({
            "clause_no": clause_no,
            "clause_title": None,
            "clause_text": clause_text,
            "summary": None,
            "tags": [],
            "page_start": scope.page_start,
            "page_end": scope.page_end,
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": source_ref,
            "source_refs": list(scope.source_refs),
            "source_label": source_label,
        })

    return entries


def _iter_entry_dicts(entries: list[dict]) -> list[dict]:
    collected: list[dict] = []

    def _visit(value: dict) -> None:
        collected.append(value)
        children = value.get("children")
        if not isinstance(children, list):
            return
        for child in children:
            if isinstance(child, dict):
                _visit(child)

    for entry in entries:
        if isinstance(entry, dict):
            _visit(entry)
    return collected


def _supplement_scope_entries_with_deterministic_inline(
    scope: ProcessingScope,
    entries: list[dict],
    *,
    allowed_clause_nos: set[str] | None = None,
) -> list[dict]:
    deterministic_entries = _deterministic_inline_clause_entries_from_scope(
        scope,
        allowed_clause_nos=allowed_clause_nos,
    )
    if not deterministic_entries:
        return entries
    if not entries:
        return deterministic_entries

    existing_clause_nos = {
        str(entry.get("clause_no") or "").strip()
        for entry in _iter_entry_dicts(entries)
        if str(entry.get("clause_no") or "").strip()
    }
    missing_entries = [
        entry
        for entry in deterministic_entries
        if str(entry.get("clause_no") or "").strip() not in existing_clause_nos
    ]
    if not missing_entries:
        return entries
    return missing_entries + entries


def _should_skip_block_for_ai(block: BlockSegment) -> bool:
    if block.segment_type in {"heading_only_block", "non_clause_block"}:
        return True
    if block.segment_type in {"commentary_block", "appendix_block"} and not block.text.strip():
        return True
    if (
        block.segment_type == "normative_clause_block"
        and block.text.strip()
        and _ACTUAL_CHAPTER_TITLE.match(block.chapter_label)
    ):
        return False
    if (
        block.segment_type != "table_requirement_block"
        and _resolved_block_clause_no(block) is None
        and not str(block.clause_no or "").strip()
    ):
        return True
    return False


_ACTUAL_CHAPTER_TITLE = re.compile(r"^\d{1,2}(?![.\d])\s*\S")
_ACTUAL_CLAUSE_TITLE = re.compile(r"^\d+(?:\.\d+)+\s+\S")
_TOC_TITLE_RE = re.compile(r"^\s*(?:目次|contents)\s*$", re.IGNORECASE)
_TOC_PAGE_REF = re.compile(r"(?:\(\d+\)|（\d+）)\s*$")
_TOC_DOT_LEADERS = re.compile(r"[.…]{2,}")
_BLOCK_CLAUSE_NO_RE = re.compile(r"^\s*((?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)+))\b")
_INLINE_SCOPE_CLAUSE_LINE_RE = re.compile(r"^\s*((?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)+))\s*(\S.*)$")
_INLINE_SCOPE_HOST_LABEL_RE = re.compile(r"^\s*((?:[1-9]\d*(?:\.\d+)*|[A-Z]))\s*(?![.．])(\S.*)$")
_INLINE_SCOPE_APPENDIX_LABEL_RE = re.compile(r"^\s*附录\s*([A-Z])\s*(\S.*)$")
_SCOPE_LABEL_SPLIT_SUFFIX_RE = re.compile(r"\s*\(\d+/\d+\)\s*$")
_STRUCTURED_CLAUSE_NO_RE = re.compile(r"^(?:[A-Z](?:\.\d+)*|\d+(?:\.\d+)*)$")
_EMBEDDED_SECTION_HEADING_RE = re.compile(
    r"^\s*((?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)+))(?![.\d])\s*(\S.*)$"
)
_LAYOUT_MARKER_RE = re.compile(r"^(?:text|text_list)$")
_PAGE_ARTIFACT_RE = re.compile(r"^[·•]?\d+[·•]?$")
_WATERMARK_RE = re.compile(r"(?:标准分享网|www\.bzfxw\.com|免费下载)")
_DETERMINISTIC_LIST_SIGNAL_RE = re.compile(r"(?:下列|如下|；|\n\s*(?:[（(]?\d+[)）]|\d+\s)|[一二三四五六七八九十]+、)")
_CLAUSE_LIKE_SECTION_CODE = re.compile(r"^(?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)*)$")
_NUMERIC_SECTION_CODE = re.compile(r"^\d+(?:\.\d+)*$")
_SECTION_TITLE_SENTENCE_SIGNAL_RE = re.compile(r"[，。；：]|应|不得|必须|严禁|禁止|宜|可")


def _section_heading_text(section: dict) -> str:
    code = str(section.get("section_code") or "").strip()
    title = str(section.get("title") or "").strip()
    return f"{code} {title}".strip()


def _section_host_code(section: dict) -> str:
    code = str(section.get("section_code") or "").strip()
    if code:
        return code

    title = str(section.get("title") or "").strip()
    if not title:
        return ""

    embedded_match = _EMBEDDED_SECTION_HEADING_RE.match(title)
    if embedded_match:
        return str(embedded_match.group(1) or "").strip()

    appendix_match = _INLINE_SCOPE_APPENDIX_LABEL_RE.match(title)
    if appendix_match:
        return str(appendix_match.group(1) or "").strip()

    host_match = re.match(r"^\s*([1-9]\d*)(?![.\d])\s*\S", title)
    if host_match:
        return str(host_match.group(1) or "").strip()

    return ""


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


def _section_level_from_code(code: str, fallback_level: object = None) -> int | object:
    normalized = str(code or "").strip()
    if not normalized:
        return fallback_level
    return normalized.count(".") + 1


def _clean_section_text_lines(text: str) -> list[str]:
    filtered: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or _LAYOUT_MARKER_RE.match(line):
            continue
        if _WATERMARK_RE.search(line):
            continue
        filtered.append(line)

    cleaned: list[str] = []
    for index, line in enumerate(filtered):
        if _PAGE_ARTIFACT_RE.match(line):
            next_line = filtered[index + 1] if index + 1 < len(filtered) else ""
            if not next_line or _WATERMARK_RE.search(next_line):
                continue
        cleaned.append(line)
    return cleaned


def _parse_numbered_item_heading(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped:
        return None

    bracketed_match = re.match(r"^[（(]\s*(\d+)\s*[）)]", stripped)
    if bracketed_match:
        code = str(bracketed_match.group(1) or "").strip()
        rest = stripped[bracketed_match.end():].lstrip("、.)） \t")
        return (code, rest) if code and rest else None

    digit_match = re.match(r"^(\d+)", stripped)
    if not digit_match:
        return None

    code = str(digit_match.group(1) or "").strip()
    next_index = digit_match.end()
    if next_index >= len(stripped):
        return None

    next_char = stripped[next_index]
    if next_char in {".", "．"}:
        return None

    if next_char in {"、", ")", "）"}:
        rest = stripped[next_index + 1:].strip()
        return (code, rest) if rest else None

    if next_char.isspace():
        rest = stripped[next_index:].strip()
        return (code, rest) if rest else None

    if next_char.isascii():
        return None

    rest = stripped[next_index:].strip()
    return (code, rest) if rest else None


def _text_invites_numbered_items(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return normalized.endswith(("：", ":")) or "下列" in normalized or "如下" in normalized


def _is_related_embedded_clause(parent_code: str, heading_code: str) -> bool:
    parent = str(parent_code or "").strip()
    heading = str(heading_code or "").strip()
    if not heading:
        return False
    if not parent:
        return True
    if heading.startswith(f"{parent}."):
        return True
    if heading.count(".") != parent.count("."):
        return False
    if "." not in parent or "." not in heading:
        return False
    return heading.rsplit(".", 1)[0] == parent.rsplit(".", 1)[0]


def _split_embedded_sections(section: dict) -> list[dict]:
    normalized = _coerce_inline_clause_text(section)
    text_lines = _clean_section_text_lines(str(normalized.get("text") or ""))
    if not text_lines:
        normalized_without_markers = dict(normalized)
        normalized_without_markers["text"] = ""
        return [_coerce_inline_clause_text(normalized_without_markers)]

    parent_code = _section_host_code(normalized)
    parent_title = str(normalized.get("title") or "").strip()
    parent_level = normalized.get("level")
    source_id = str(normalized.get("id") or "").strip()
    expanded: list[dict] = []
    synthetic_index = 0
    leading_lines: list[str] = []

    def _next_id() -> str | None:
        nonlocal synthetic_index
        if not source_id:
            return None
        synthetic_index += 1
        return f"{source_id}#{synthetic_index}"

    def _append_section(
        payload: dict,
        body_lines: list[str],
        *,
        combine_title_into_text: bool = False,
    ) -> None:
        candidate = dict(payload)
        body_text = "\n".join(line for line in body_lines if line).strip()
        if combine_title_into_text and body_text:
            title = str(candidate.get("title") or "").strip()
            candidate["text"] = "\n".join(part for part in (title, body_text) if part).strip()
        else:
            candidate["text"] = body_text
        if (
            not str(candidate.get("section_code") or "").strip()
            and not str(candidate.get("title") or "").strip()
            and not str(candidate.get("text") or "").strip()
        ):
            return
        expanded.append(_coerce_inline_clause_text(candidate))

    active_payload: dict | None = dict(normalized) if parent_code else None
    active_body: list[str] = []
    active_kind = "section" if active_payload is not None else None
    active_invites_items = _text_invites_numbered_items(parent_title)
    active_combine_title = False

    for line in text_lines:
        clause_match = _EMBEDDED_SECTION_HEADING_RE.match(line)
        heading_code = clause_match.group(1) if clause_match else None
        heading_title = clause_match.group(2).strip() if clause_match else None
        if heading_code and _is_related_embedded_clause(parent_code, heading_code):
            if active_payload is not None:
                _append_section(
                    active_payload,
                    active_body,
                    combine_title_into_text=active_combine_title,
                )
            elif leading_lines:
                preamble_payload = dict(normalized)
                _append_section(preamble_payload, leading_lines)
                leading_lines = []

            active_payload = dict(normalized)
            synthetic_id = _next_id()
            if synthetic_id:
                active_payload["id"] = synthetic_id
            active_payload["section_code"] = heading_code
            active_payload["title"] = heading_title
            active_payload["level"] = _section_level_from_code(heading_code, parent_level)
            active_body = []
            active_kind = "section"
            active_invites_items = _text_invites_numbered_items(heading_title)
            active_combine_title = True
            continue

        item_heading = _parse_numbered_item_heading(line)
        if item_heading and (
            active_payload is None
            or active_kind == "item"
            or active_invites_items
        ):
            if active_payload is not None:
                _append_section(
                    active_payload,
                    active_body,
                    combine_title_into_text=active_combine_title,
                )
            elif leading_lines:
                preamble_payload = dict(normalized)
                _append_section(preamble_payload, leading_lines)
                leading_lines = []

            item_code, item_title = item_heading
            active_payload = dict(normalized)
            synthetic_id = _next_id()
            if synthetic_id:
                active_payload["id"] = synthetic_id
            active_payload["section_code"] = item_code
            active_payload["title"] = item_title
            active_payload["level"] = (
                parent_level + 1
                if isinstance(parent_level, int)
                else parent_level
            )
            active_body = []
            active_kind = "item"
            active_invites_items = False
            active_combine_title = False
            continue

        if active_payload is not None:
            active_body.append(line)
        else:
            leading_lines.append(line)

    if active_payload is not None:
        _append_section(
            active_payload,
            active_body,
            combine_title_into_text=active_combine_title,
        )
    elif leading_lines:
        preamble_payload = dict(normalized)
        _append_section(preamble_payload, leading_lines)

    if not expanded:
        return [normalized]
    return expanded


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
    if _TOC_TITLE_RE.match(title):
        return True
    if _TOC_PAGE_REF.search(title):
        return True
    if _TOC_DOT_LEADERS.search(title):
        return True
    text = (section.get("text") or "").strip()
    toc_like_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]
    if sum(1 for line in toc_like_lines if _TOC_PAGE_REF.search(line) or _TOC_DOT_LEADERS.search(line)) >= 2:
        return True
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

    normalized: list[dict] = []
    for section in sections[start_idx:]:
        if _is_toc_heading(section):
            continue
        normalized.extend(_split_embedded_sections(section))

    normalized = clean_sections(normalized, drop_toc_noise=False)
    normalized = [
        {**section, "sort_order": index}
        for index, section in enumerate(normalized)
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
        "temperature": 0.0,
        "max_tokens": None,
    }

    # Apply per-agent credentials as overrides
    if config.base_url and config.api_key:
        payload["primary_override"] = {
            "base_url": config.base_url,
            "api_key": config.api_key,
            "model": config.primary_model or "deepseek-v4-flash",
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
    def _coerce_entries(value: object) -> tuple[list[dict], bool]:
        if isinstance(value, dict):
            return [value], False
        if isinstance(value, list):
            entries = [item for item in value if isinstance(item, dict)]
            if entries:
                return entries, False
            if not value:
                # Some appendix/table-only scopes legitimately have no clause entries.
                return [], True
        return [], False

    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        entries, accepted_empty = _coerce_entries(result)
        if entries or accepted_empty:
            return entries
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for target in ("[", "{"):
            for index, char in enumerate(text):
                if char != target:
                    continue
                try:
                    result, _end = decoder.raw_decode(text[index:])
                    entries, accepted_empty = _coerce_entries(result)
                    if entries or accepted_empty:
                        return entries
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
    *,
    ai_artifacts: list[AiResponseArtifact] | None = None,
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
        if ai_artifacts is not None:
            ai_artifacts.append(
                AiResponseArtifact(
                    task_type="tag_clauses",
                    prompt_mode="legacy_extract",
                    scope_label=current_scope.chapter_label,
                    prompt=prompt,
                    raw_response=raw_response,
                    parsed_count=len(entries),
                    source_refs=list(current_scope.source_refs),
                )
            )
        for entry in entries:
            _apply_scope_defaults(entry, current_scope)
        all_entries.extend(entries)

    return all_entries


def _process_scope_collecting_artifacts(
    conn: Connection,
    scope: ProcessingScope,
    *,
    ai_artifacts: list[AiResponseArtifact],
) -> list[dict]:
    try:
        return _process_scope_with_retries(conn, scope, ai_artifacts=ai_artifacts)
    except TypeError as exc:
        if "ai_artifacts" not in str(exc):
            raise
        return _process_scope_with_retries(conn, scope)


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


def _iter_clause_source_refs(clause: dict) -> list[str]:
    refs: list[str] = []
    source_ref = clause.get("source_ref")
    if isinstance(source_ref, str) and source_ref.strip():
        refs.append(source_ref.strip())
    source_refs = clause.get("source_refs")
    if isinstance(source_refs, list):
        for value in source_refs:
            if isinstance(value, str) and value.strip():
                refs.append(value.strip())
    return refs


def _normalize_page_anchor(value: object) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    return None


def _normalize_source_ref_for_page_lookup(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if normalized.startswith("document_section:"):
        return normalized.split("#", 1)[0]
    return normalized


def _compact_anchor_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", "", text)


def _is_toc_like_anchor_page(text: object) -> bool:
    raw_text = str(text or "").strip()
    if not raw_text:
        return False
    lowered = raw_text.lower()
    if "目次" in raw_text or "contents" in lowered:
        return True
    toc_marker_count = sum(
        1
        for line in raw_text.splitlines()
        if _TOC_PAGE_REF.search(line.strip()) or _TOC_DOT_LEADERS.search(line.strip())
    )
    return toc_marker_count >= 2


def _candidate_anchor_snippets(clause: dict) -> list[str]:
    candidates: list[str] = []

    def _add(value: object, *, min_len: int = 8, max_len: int = 120) -> None:
        compact = _compact_anchor_text(value)
        if len(compact) < min_len:
            return
        compact = compact[:max_len]
        if compact not in candidates:
            candidates.append(compact)

    _add(clause.get("source_label"), min_len=10, max_len=160)
    _add(clause.get("clause_title"), min_len=6, max_len=80)

    clause_text = str(clause.get("clause_text") or "").strip()
    if clause_text:
        first_line = clause_text.splitlines()[0].strip()
        _add(first_line, min_len=6, max_len=100)
        first_sentence = re.split(r"[。；：!?！？\n]", clause_text, maxsplit=1)[0].strip()
        _add(first_sentence, min_len=6, max_len=80)

    clause_no = _compact_anchor_text(clause.get("clause_no"))
    if clause_no and clause_no not in candidates:
        candidates.append(clause_no)

    return candidates


def _resolve_clause_page_range_from_asset(clause: dict, document_asset) -> tuple[int | None, int | None]:
    resolved_pages: list[int] = []
    table_ranges: list[tuple[int, int]] = []

    page_refs: dict[str, set[int]] = {}
    for page in document_asset.pages:
        page_number = _normalize_page_anchor(page.page_number)
        if page_number is None:
            continue
        ref = _normalize_source_ref_for_page_lookup(page.source_ref)
        if not ref:
            continue
        page_refs.setdefault(ref, set()).add(page_number)

    table_refs: dict[str, tuple[int | None, int | None]] = {
        str(table.source_ref): (
            _normalize_page_anchor(table.page_start),
            _normalize_page_anchor(table.page_end),
        )
        for table in document_asset.tables
        if isinstance(table.source_ref, str) and table.source_ref.strip()
    }

    for ref in _iter_clause_source_refs(clause):
        normalized_ref = _normalize_source_ref_for_page_lookup(ref)
        for page_number in sorted(page_refs.get(normalized_ref, set())):
            resolved_pages.append(page_number)
        table_range = table_refs.get(ref)
        if table_range and table_range[0] is not None:
            table_ranges.append((
                table_range[0],
                table_range[1] if table_range[1] is not None else table_range[0],
            ))

    if resolved_pages:
        return min(resolved_pages), max(resolved_pages)
    if table_ranges:
        starts = [start for start, _ in table_ranges]
        ends = [end for _, end in table_ranges]
        return min(starts), max(ends)

    compact_pages = [
        (page_number, _compact_anchor_text(page.normalized_text))
        for page in document_asset.pages
        for page_number in [_normalize_page_anchor(page.page_number)]
        if page_number is not None and not _is_toc_like_anchor_page(page.normalized_text)
    ]

    for snippet in _candidate_anchor_snippets(clause):
        matches = [
            page_number
            for page_number, compact_text in compact_pages
            if compact_text and snippet in compact_text
        ]
        if matches:
            return min(matches), max(matches)

    return None, None


def _backfill_clause_page_anchors_from_asset(clauses: list[dict], document_asset) -> list[dict]:
    if not clauses:
        return clauses

    for clause in clauses:
        current_start = _normalize_page_anchor(clause.get("page_start"))
        current_end = _normalize_page_anchor(clause.get("page_end"))
        if current_start is not None and current_end is not None:
            continue
        inferred_start, inferred_end = _resolve_clause_page_range_from_asset(clause, document_asset)
        if inferred_start is not None:
            clause["page_start"] = inferred_start
            clause["page_end"] = inferred_end if inferred_end is not None else inferred_start

    clause_by_id = {
        clause["id"]: clause
        for clause in clauses
        if clause.get("id") is not None
    }
    children_by_parent: dict[UUID, list[dict]] = {}
    for clause in clauses:
        parent_id = clause.get("parent_id")
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(clause)

    changed = True
    while changed:
        changed = False
        for clause in clauses:
            start = _normalize_page_anchor(clause.get("page_start"))
            end = _normalize_page_anchor(clause.get("page_end"))
            if start is None or end is None:
                parent = clause_by_id.get(clause.get("parent_id"))
                parent_start = _normalize_page_anchor(parent.get("page_start")) if parent else None
                parent_end = _normalize_page_anchor(parent.get("page_end")) if parent else None
                if parent_start is not None and parent_end is not None:
                    clause["page_start"] = parent_start
                    clause["page_end"] = parent_end
                    changed = True
                    continue

            if start is not None and end is not None:
                continue
            child_pages = [
                (
                    _normalize_page_anchor(child.get("page_start")),
                    _normalize_page_anchor(child.get("page_end")),
                )
                for child in children_by_parent.get(clause.get("id"), [])
            ]
            anchored_children = [
                (child_start, child_end)
                for child_start, child_end in child_pages
                if child_start is not None and child_end is not None
            ]
            if anchored_children:
                clause["page_start"] = min(child_start for child_start, _ in anchored_children)
                clause["page_end"] = max(child_end for _, child_end in anchored_children)
                changed = True

    return clauses


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
    force_persist_failed_quality: bool = False,
) -> dict:
    """Run the AI extraction phase using existing OCR sections."""
    started_at = time.time()
    settings = get_settings()

    try:
        standard = _std_repo.get_standard(conn, standard_id)
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
        parse_plugins = _parse_skill_plugins()
        active_skill_names = _active_parse_skill_names(conn)
        executed_skills: list[ExecutedParseSkill] = []
        skill_context = ParseSkillContext(
            standard=standard,
            document_id=document_id,
            document_asset=document_asset,
            raw_sections=raw_sections,
            tables=tables,
        )
        executed_skills.extend(run_parse_skill_hooks(
            hook="preflight_parse_asset",
            context=skill_context,
            plugins=parse_plugins,
            active_skill_names=active_skill_names,
        ))
        if _has_blocking_skill_failure(executed_skills):
            elapsed = time.time() - started_at
            return {
                "standard_id": str(standard_id),
                "status": "needs_review",
                "total_clauses": 0,
                "normative": 0,
                "commentary": 0,
                "scopes_processed": 0,
                "warnings": [
                    message
                    for skill in executed_skills
                    for message in skill.messages
                ][:5],
                "executed_skills": _serialize_executed_skills(executed_skills),
                "elapsed_seconds": round(elapsed, 1),
            }
        executed_skills.extend(run_parse_skill_hooks(
            hook="cleanup_parse_asset",
            context=skill_context,
            plugins=parse_plugins,
            active_skill_names=active_skill_names,
        ))
        executed_skills.extend(run_parse_skill_hooks(
            hook="before_profile_resolve",
            context=skill_context,
            plugins=parse_plugins,
            active_skill_names=active_skill_names,
        ))
        profile = resolve_standard_profile(standard, document_asset)
        use_single_standard_block_path = _should_use_single_standard_block_path(profile, raw_sections)
        sections = _normalize_sections_for_processing(raw_sections)
        if not sections:
            raise ValueError("No normalized sections available for processing")
        known_clause_nos = _collect_known_clause_nos(sections)
        outline_clause_nos = (
            collect_outline_clause_nos_from_pages(document_asset.pages)
            | _collect_outline_clause_nos(raw_sections)
        )
        if use_single_standard_block_path:
            logger.info("single_standard_block_path_enabled", standard_id=str(standard_id))
            block_tables = _serialize_asset_tables_for_block_path(document_asset)
            blocks = _build_profile_blocks(sections, block_tables, profile=profile)
            block_type_counts: dict[str, int] = {}
            for block in blocks:
                block_type_counts[block.segment_type] = block_type_counts.get(block.segment_type, 0) + 1
            logger.info("single_standard_blocks_built", counts=block_type_counts)
            executed_skills.extend(run_parse_skill_hooks(
                hook="after_block_parse",
                context=skill_context,
                plugins=parse_plugins,
                active_skill_names=active_skill_names,
            ))

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
            executed_skills.extend(run_parse_skill_hooks(
                hook="after_block_parse",
                context=skill_context,
                plugins=parse_plugins,
                active_skill_names=active_skill_names,
            ))
        if not scopes and not deterministic_entries:
            raise ValueError("No processing scopes generated")

        all_entries: list[dict] = list(deterministic_entries)
        ai_artifacts: list[AiResponseArtifact] = []
        ai_fallback_count = 0
        for i, scope in enumerate(scopes):
            current_block = blocks[i] if use_single_standard_block_path else None
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
                _deterministic_entries_from_block(
                    current_block,
                    table_strategy=profile.table_requirement_strategy,
                )
                if current_block is not None
                else _deterministic_entries_from_scope(
                    scope,
                    table_strategy=profile.table_requirement_strategy,
                )
            )
            direct_entries = _sanitize_scope_entries(
                scope,
                direct_entries,
                allowed_clause_nos=known_clause_nos,
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

            ai_fallback_count += 1
            entries = _process_scope_collecting_artifacts(
                conn,
                scope,
                ai_artifacts=ai_artifacts,
            )
            entries = _sanitize_scope_entries(
                scope,
                entries,
                allowed_clause_nos=known_clause_nos,
            )
            supplemented_entries = _supplement_scope_entries_with_deterministic_inline(
                scope,
                entries,
                allowed_clause_nos=known_clause_nos,
            )
            if supplemented_entries is not entries:
                entries = supplemented_entries
                logger.info(
                    "processing_scope_deterministic_fallback",
                    index=i + 1,
                    total=len(scopes),
                    scope_type=scope.scope_type,
                    chapter=scope.chapter_label,
                    entry_count=len(entries),
                )
            all_entries.extend(entries)

            if i < len(scopes) - 1:
                delay_seconds = _scope_delay_seconds()
                if delay_seconds > 0:
                    time.sleep(delay_seconds)

        if use_single_standard_block_path:
            all_entries.extend(_seed_section_title_entries(sections))

        logger.info("all_scopes_processed", total_entries=len(all_entries))

        clauses = build_tree(all_entries, standard_id)
        clauses = _prune_empty_outline_hosts(clauses, outline_clause_nos=outline_clause_nos)
        clauses = _backfill_clause_page_anchors_from_asset(clauses, document_asset)
        clauses = link_commentary(clauses)
        structured_validation = validate_clauses(clauses, outline_clause_nos=outline_clause_nos)
        repair_tasks = (
            build_repair_tasks(clauses, structured_validation.issues)
            if getattr(settings, "standard_repair_enabled", True)
            else []
        )
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
        quality_report = build_standard_quality_report(
            document_asset=document_asset,
            raw_sections=raw_sections,
            normalized_sections=sections,
            tables=tables,
            clauses=clauses,
            validation=revalidated,
            warnings=combined_warnings,
            executed_skills=_serialize_executed_skills(executed_skills),
            ai_fallback_count=ai_fallback_count,
            total_parser_block_count=len(scopes) if use_single_standard_block_path else 0,
            max_ai_fallback_ratio=float(
                profile.quality_thresholds.get("max_ai_fallback_ratio", 0.15)
            ),
        )
        skill_context.clauses = clauses
        skill_context.validation = revalidated
        executed_skills.extend(run_parse_skill_hooks(
            hook="after_validation",
            context=skill_context,
            plugins=parse_plugins,
            active_skill_names=active_skill_names,
        ))
        if _has_blocking_skill_failure(executed_skills):
            quality_report["executed_skills"] = _serialize_executed_skills(executed_skills)
            elapsed = time.time() - started_at
            return {
                "standard_id": str(standard_id),
                "status": "needs_review",
                "total_clauses": 0,
                "normative": sum(1 for c in clauses if c["clause_type"] == "normative"),
                "commentary": sum(1 for c in clauses if c["clause_type"] == "commentary"),
                "scopes_processed": len(scopes),
                "repair_task_count": len(repair_tasks),
                "issues_before_repair": len(structured_validation.issues),
                "issues_after_repair": len(revalidated.issues),
                "warnings": combined_warnings[:5],
                "validation": revalidated.to_dict(),
                "quality_report": quality_report,
                "executed_skills": _serialize_executed_skills(executed_skills),
                "ai_response_artifacts": serialize_ai_response_artifacts(ai_artifacts),
                "elapsed_seconds": round(elapsed, 1),
            }
        executed_skills.extend(run_parse_skill_hooks(
            hook="recovery_diagnostics",
            context=skill_context,
            plugins=parse_plugins,
            active_skill_names=active_skill_names,
        ))
        quality_report["executed_skills"] = _serialize_executed_skills(executed_skills)
        quality_status = str((quality_report.get("overview") or {}).get("status") or "")
        if quality_status == "fail" and not force_persist_failed_quality:
            elapsed = time.time() - started_at
            return {
                "standard_id": str(standard_id),
                "status": "needs_review",
                "total_clauses": 0,
                "normative": sum(1 for c in clauses if c["clause_type"] == "normative"),
                "commentary": sum(1 for c in clauses if c["clause_type"] == "commentary"),
                "scopes_processed": len(scopes),
                "repair_task_count": len(repair_tasks),
                "issues_before_repair": len(structured_validation.issues),
                "issues_after_repair": len(revalidated.issues),
                "repair_error": repair_error,
                "warnings": combined_warnings[:5],
                "validation": revalidated.to_dict(),
                "quality_report": quality_report,
                "executed_skills": _serialize_executed_skills(executed_skills),
                "ai_response_artifacts": serialize_ai_response_artifacts(ai_artifacts),
                "elapsed_seconds": round(elapsed, 1),
            }

        _std_repo.delete_clauses(conn, standard_id)
        inserted = _std_repo.bulk_create_clauses(conn, clauses)

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
            "quality_report": quality_report,
            "executed_skills": _serialize_executed_skills(executed_skills),
            "ai_response_artifacts": serialize_ai_response_artifacts(ai_artifacts),
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
