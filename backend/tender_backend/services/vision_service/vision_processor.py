"""Vision-based standard PDF extraction using Qwen3-VL.

Replaces the MinerU OCR → regex → LLM text pipeline with a single-step
vision model extraction: PDF → PNG per page → Qwen3-VL → structured JSON.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import UUID

import httpx
import structlog
from psycopg import Connection

from tender_backend.core.config import get_settings
from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.tree_builder import build_tree, link_commentary, validate_tree
from tender_backend.services.vision_service.page_merger import merge_page_results
from tender_backend.services.vision_service.pdf_renderer import PageImage, render_pdf_to_pages
from tender_backend.services.vision_service.vision_prompt import build_vision_messages

logger = structlog.stdlib.get_logger(__name__)

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:8001")

_std_repo = StandardRepository()
_agent_repo = AgentConfigRepository()


# ── Helpers ──


def _get_pdf_path(conn: Connection, document_id: str) -> str | None:
    """Look up the local file path for a document's source PDF.

    Mirrors ``norm_processor._get_pdf_path`` — kept here to avoid a
    circular import from the norm_service module.
    """
    from tender_backend.services.storage_service.project_file_storage import ProjectFileStorage
    from psycopg.rows import dict_row

    storage = ProjectFileStorage()
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
    resolved = storage.resolve_local_path(row["storage_key"])
    return str(resolved) if resolved else None


def _ai_gateway_chat_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api"):
        return f"{normalized}/ai/chat"
    return f"{normalized}/api/ai/chat"


def _parse_llm_json(raw: str) -> list[dict]:
    """Extract a JSON array from VL model response (handles markdown fences)."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning("vision_json_parse_failed", raw_length=len(raw))
    return []


# ── AI gateway call ──


def _call_vision_model(
    conn: Connection,
    page: PageImage,
) -> list[dict]:
    """Send a single page image to Qwen3-VL via the AI Gateway.

    Returns parsed clause entries for that page (may be empty for TOC/cover pages).
    """
    config = _agent_repo.get_by_key(conn, "tag_clauses")

    messages = build_vision_messages(page)
    settings = get_settings()

    payload: dict[str, Any] = {
        "task_type": "vision_extract_clauses",
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 8192,
    }

    # Use SiliconFlow credentials from agent config (same provider for VL model).
    if config and config.base_url and config.api_key:
        payload["primary_override"] = {
            "base_url": config.base_url,
            "api_key": config.api_key,
            "model": "Qwen/Qwen3-VL-8B-Instruct",
        }
    if config and config.fallback_base_url and config.fallback_api_key:
        payload["fallback_override"] = {
            "base_url": config.fallback_base_url,
            "api_key": config.fallback_api_key,
            "model": "Qwen/Qwen3-VL-8B-Instruct",
        }

    url = _ai_gateway_chat_url(AI_GATEWAY_URL)
    timeout = settings.vision_ai_gateway_timeout_seconds
    resp = httpx.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    content = data.get("content", "")
    logger.info(
        "vision_page_response",
        page=page.page_number,
        model=data.get("resolved_model"),
        input_tokens=data.get("input_tokens", 0),
        output_tokens=data.get("output_tokens", 0),
    )
    return _parse_llm_json(content)


def _process_page_with_retry(
    conn: Connection,
    page: PageImage,
    *,
    max_retries: int = 1,
) -> tuple[int, list[dict]]:
    """Process a single page with retry on failure.

    Returns ``(page_number, entries)``.
    """
    for attempt in range(max_retries + 1):
        try:
            entries = _call_vision_model(conn, page)
            return page.page_number, entries
        except Exception as exc:
            if attempt < max_retries:
                delay = 2 ** attempt
                logger.warning(
                    "vision_page_retry",
                    page=page.page_number,
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(exc),
                )
                time.sleep(delay)
            else:
                logger.error(
                    "vision_page_failed",
                    page=page.page_number,
                    error=str(exc),
                )
                return page.page_number, []


# ── Main pipeline ──


def process_standard_vision(
    conn: Connection,
    *,
    standard_id: UUID,
    document_id: str,
    max_concurrent: int | None = None,
) -> dict:
    """Process a standard PDF using Qwen3-VL vision extraction.

    Steps:
        1. Resolve PDF path from *document_id*.
        2. Render all pages to PNG.
        3. Call Qwen3-VL for each page (concurrently).
        4. Merge cross-page continuations.
        5. Build clause tree via existing ``tree_builder``.
        6. Persist clauses and index to OpenSearch.

    Returns a summary dict compatible with ``process_standard_ai``.
    """
    settings = get_settings()
    if max_concurrent is None:
        max_concurrent = settings.vision_max_concurrent_pages
    started_at = time.time()

    try:
        # 1. Resolve PDF
        pdf_path = _get_pdf_path(conn, document_id)
        if not pdf_path:
            raise FileNotFoundError(f"PDF not found for document {document_id}")

        # 2. Render pages
        logger.info("rendering_pdf", standard_id=str(standard_id), pdf_path=pdf_path)
        pages = render_pdf_to_pages(pdf_path, dpi=settings.vision_page_dpi)
        logger.info("pdf_rendered", page_count=len(pages))

        # 3. Concurrent vision extraction
        page_results: list[tuple[int, list[dict]]] = []
        delay_ms = settings.vision_page_delay_ms

        with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
            futures = {}
            for i, page in enumerate(pages):
                future = pool.submit(_process_page_with_retry, conn, page)
                futures[future] = page.page_number

                # Optional throttle between submissions.
                if delay_ms > 0 and i < len(pages) - 1:
                    time.sleep(delay_ms / 1000.0)

            for future in as_completed(futures):
                page_num = futures[future]
                try:
                    result = future.result()
                    page_results.append(result)
                except Exception as exc:
                    logger.error("vision_future_failed", page=page_num, error=str(exc))
                    page_results.append((page_num, []))

        pages_with_entries = sum(1 for _, entries in page_results if entries)
        logger.info(
            "vision_extraction_done",
            total_pages=len(pages),
            pages_with_entries=pages_with_entries,
        )

        # 4. Merge cross-page continuations
        all_entries = merge_page_results(page_results)

        # Set source metadata (vision pipeline marker).
        for entry in all_entries:
            entry.setdefault("clause_type", "normative")
            entry.setdefault("source_type", "vision")
            entry.setdefault("source_label", "vision-extraction")

        logger.info("entries_merged", total_entries=len(all_entries))

        if not all_entries:
            raise ValueError("Vision extraction produced no entries")

        # 5. Build tree (reuse existing logic)
        clauses = build_tree(all_entries, standard_id)
        clauses = link_commentary(clauses)
        warnings = validate_tree(clauses)

        # 6. Persist
        _std_repo.delete_clauses(conn, standard_id)
        inserted = _std_repo.bulk_create_clauses(conn, clauses)

        # 7. Index (best-effort)
        standard = _std_repo.get_standard(conn, standard_id)
        _index_clauses(standard, clauses)

        elapsed = time.time() - started_at
        return {
            "standard_id": str(standard_id),
            "status": "completed",
            "pipeline": "vision",
            "total_clauses": inserted,
            "normative": sum(1 for c in clauses if c["clause_type"] == "normative"),
            "commentary": sum(1 for c in clauses if c["clause_type"] == "commentary"),
            "pages_processed": len(pages),
            "pages_with_entries": pages_with_entries,
            "warnings": warnings[:5],
            "elapsed_seconds": round(elapsed, 1),
        }

    except Exception as exc:
        logger.exception("vision_processing_failed", standard_id=str(standard_id), error=str(exc))
        raise


def _index_clauses(standard: dict | None, clauses: list[dict]) -> None:
    """Index clauses to OpenSearch (best-effort)."""
    if not standard or not clauses:
        return
    try:
        import asyncio

        from tender_backend.services.search_service.index_manager import IndexManager
        from tender_backend.tools.reindex_standard_clauses import build_clause_index_docs

        manager = IndexManager()
        docs = build_clause_index_docs(standard, clauses)
        asyncio.get_event_loop().run_until_complete(
            manager.bulk_index("clause_index", docs)
        )
    except Exception:
        logger.warning("opensearch_indexing_failed", exc_info=True)
