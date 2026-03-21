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
from tender_backend.services.norm_service.layout_compressor import compress_sections
from tender_backend.services.norm_service.prompt_builder import build_prompt
from tender_backend.services.norm_service.scope_splitter import ProcessingScope, rebalance_scopes, split_into_scopes
from tender_backend.services.norm_service.tree_builder import build_tree, link_commentary, validate_tree
from tender_backend.services.search_service.index_manager import IndexManager
from tender_backend.services.storage_service.project_file_storage import ProjectFileStorage
from tender_backend.tools.reindex_standard_clauses import build_clause_index_docs

logger = structlog.stdlib.get_logger(__name__)

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:8001")

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
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            if any(_extract_page_text(item) for item in payload):
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
        for key in ("markdown", "md", "text", "content", "raw_text", "raw_markdown"):
            if key in value:
                fragments.extend(_collect_text_fragments(value[key]))
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
    from tender_backend.services.parse_service.parser import persist_sections

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

            sections = _mineru_to_sections(raw_content, pages)
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
        if page_index is not None:
            page_cursor = page_index
            page_number = normalized_pages[page_index]["page_number"]

        sections.append({
            "section_code": code,
            "title": title,
            "level": level,
            "page_start": page_number,
            "page_end": page_number,
            "text": text,
        })

    return sections


# ── Section fetching ──

def _fetch_sections(conn: Connection, document_id: str) -> list[dict]:
    """Fetch all document_section rows for a document."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT id, section_code, title, level, text,
                      page_start, page_end
               FROM document_section
               WHERE document_id = %s
               ORDER BY
                   CASE WHEN page_start IS NULL THEN 1 ELSE 0 END,
                   page_start,
                   ctid""",
            (document_id,),
        ).fetchall()


_ACTUAL_CHAPTER_TITLE = re.compile(r"^\d+\s+\S")
_TOC_PAGE_REF = re.compile(r"(?:\(\d+\)|（\d+）)\s*$")
_TOC_DOT_LEADERS = re.compile(r"[.…]{2,}")


def _is_toc_heading(section: dict) -> bool:
    title = (section.get("title") or "").strip()
    text = (section.get("text") or "").strip()
    if text:
        return False
    if _TOC_PAGE_REF.search(title):
        return True
    if _TOC_DOT_LEADERS.search(title):
        return True
    return False


def _normalize_sections_for_processing(sections: list[dict]) -> list[dict]:
    """Trim front matter and drop empty TOC headings before clause extraction."""
    if not sections:
        return []

    start_idx = 0
    for idx, section in enumerate(sections):
        title = (section.get("title") or "").strip()
        if _ACTUAL_CHAPTER_TITLE.match(title) and not _is_toc_heading(section):
            start_idx = idx
            break

    normalized = [
        section
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
        # Try to find JSON array in text
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning("llm_json_parse_failed", raw_length=len(raw))
    return []


def _is_retryable_ai_gateway_status(exc: httpx.HTTPStatusError) -> bool:
    response = exc.response
    if response.status_code not in {502, 504}:
        return False

    payload = ""
    try:
        payload = json.dumps(response.json(), ensure_ascii=False)
    except Exception:
        payload = response.text

    haystack = f"{str(exc)} {payload}".lower()
    return "timed out" in haystack or "timeout" in haystack


def _process_scope_with_retries(
    conn: Connection,
    scope: ProcessingScope,
) -> list[dict]:
    """Process one scope and split it into smaller chunks when the provider times out."""
    pending_scopes = [scope]
    all_entries: list[dict] = []

    while pending_scopes:
        current_scope = pending_scopes.pop(0)
        prompt = build_prompt(current_scope)
        try:
            raw_response = _call_ai_gateway(conn, prompt, current_scope.chapter_label)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and not _is_retryable_ai_gateway_status(exc):
                raise
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
            pending_scopes = retry_scopes + pending_scopes
            continue

        entries = _parse_llm_json(raw_response)
        for entry in entries:
            entry["clause_type"] = current_scope.scope_type
            if entry.get("page_start") is None:
                entry["page_start"] = current_scope.page_start
        all_entries.extend(entries)

    return all_entries


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
        sections = _fetch_sections(conn, document_id)
        if not sections:
            raise ValueError(f"No OCR sections available for document {document_id}")
        sections = _normalize_sections_for_processing(sections)
        if not sections:
            raise ValueError("No normalized sections available for processing")

        logger.info("processing_started", standard_id=str(standard_id), section_count=len(sections))

        windows = compress_sections(sections)
        scopes = split_into_scopes(windows)
        scopes = rebalance_scopes(scopes)
        if not scopes:
            raise ValueError("No processing scopes generated")

        all_entries: list[dict] = []
        for i, scope in enumerate(scopes):
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

        logger.info("all_scopes_processed", total_entries=len(all_entries))

        clauses = build_tree(all_entries, standard_id)
        clauses = link_commentary(clauses)
        warnings = validate_tree(clauses)

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
            "warnings": warnings[:5],
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

        asyncio.get_event_loop().run_until_complete(
            manager.bulk_index("clause_index", docs)
        )
    except Exception:
        logger.warning("opensearch_indexing_failed", exc_info=True)
