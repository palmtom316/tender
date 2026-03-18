"""Orchestrator: MinerU parse → compress → split → per-scope AI → merge → validate → persist + index.

This is the core processing pipeline for standard PDFs.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from uuid import UUID

import httpx
import structlog
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.layout_compressor import compress_sections
from tender_backend.services.norm_service.prompt_builder import build_prompt
from tender_backend.services.norm_service.scope_splitter import ProcessingScope, split_into_scopes
from tender_backend.services.norm_service.tree_builder import build_tree, link_commentary, validate_tree
from tender_backend.services.search_service.index_manager import IndexManager

logger = structlog.stdlib.get_logger(__name__)

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:8001")

_std_repo = StandardRepository()
_agent_repo = AgentConfigRepository()


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
    return row["storage_key"] if row else None


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
    headers = {"Authorization": f"Bearer {config.api_key}"}

    # Step 1: Submit PDF to MinerU
    logger.info("mineru_submitting", document_id=document_id, url=base_url)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    import base64
    payload = {
        "file": base64.b64encode(pdf_bytes).decode(),
        "filename": os.path.basename(pdf_path),
        "is_ocr": True,
        "enable_table": True,
        "language": "ch",
    }
    resp = httpx.post(base_url, json=payload, headers=headers, timeout=60.0)
    resp.raise_for_status()
    task_data = resp.json()

    # Extract task ID from response
    task_id = (
        task_data.get("data", {}).get("task_id")
        or task_data.get("task_id")
        or task_data.get("id")
    )
    if not task_id:
        # Some MinerU APIs return the task ID directly
        logger.warning("mineru_response_format", data=task_data)
        raise RuntimeError(f"MinerU did not return a task_id: {task_data}")

    logger.info("mineru_task_submitted", task_id=task_id)

    # Step 2: Poll for completion (up to 10 minutes)
    result_url = f"{base_url}/{task_id}"
    max_wait = 600
    poll_interval = 5
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        resp = httpx.get(result_url, headers=headers, timeout=30.0)
        if resp.status_code == 404:
            continue  # Not ready yet
        resp.raise_for_status()
        result = resp.json()

        status = (
            result.get("data", {}).get("state")
            or result.get("status")
            or result.get("state")
            or ""
        )
        logger.info("mineru_poll", task_id=task_id, status=status, elapsed=elapsed)

        if status in ("done", "completed", "success"):
            # Extract sections from result
            data = result.get("data", result)
            raw_content = data.get("content") or data.get("md_content") or ""
            pages = data.get("pages", [])

            # Convert MinerU output to sections
            sections = _mineru_to_sections(raw_content, pages)
            count = persist_sections(conn, document_id=UUID(document_id), sections=sections)
            logger.info("mineru_sections_persisted", document_id=document_id, count=count)
            return count

        if status in ("failed", "error"):
            error_msg = (
                result.get("data", {}).get("error")
                or result.get("error")
                or "Unknown MinerU error"
            )
            raise RuntimeError(f"MinerU parsing failed: {error_msg}")

    raise TimeoutError(f"MinerU parsing timed out after {max_wait}s for task {task_id}")


def _mineru_to_sections(content: str, pages: list[dict]) -> list[dict]:
    """Convert MinerU markdown content to section dicts for persist_sections."""
    import re

    if not content:
        return []

    sections: list[dict] = []
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

        sections.append({
            "section_code": code,
            "title": title,
            "level": level,
            "page_start": None,
            "page_end": None,
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
               ORDER BY page_start, level, section_code""",
            (document_id,),
        ).fetchall()


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

    url = f"{AI_GATEWAY_URL}/ai/chat"
    resp = httpx.post(url, json=payload, timeout=120.0)
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


def process_standard(
    conn: Connection,
    standard_id: UUID,
    document_id: str,
) -> dict:
    """Full processing pipeline for a standard document.

    Steps:
      1. Update status → parsing
      2. Fetch document sections
      3. Compress into page windows
      4. Split into processing scopes
      5. For each scope, call AI Gateway
      6. Merge results, build tree, link commentary
      7. Persist clauses to DB
      8. Index to OpenSearch
      9. Update status → completed

    Returns a summary dict.
    """
    started_at = time.time()

    # 1. Update status to parsing
    _std_repo.update_processing_status(conn, standard_id, "parsing")

    try:
        # 2. Fetch parsed sections (or parse via MinerU if none exist)
        sections = _fetch_sections(conn, document_id)
        if not sections:
            logger.info("no_sections_found_triggering_mineru", document_id=document_id)
            count = _parse_via_mineru(conn, document_id)
            logger.info("mineru_parsing_complete", section_count=count)
            sections = _fetch_sections(conn, document_id)
            if not sections:
                raise ValueError(
                    f"MinerU returned 0 parseable sections for document {document_id}"
                )

        # Update status to processing (AI extraction phase)
        _std_repo.update_processing_status(conn, standard_id, "processing")

        logger.info("processing_started", standard_id=str(standard_id), section_count=len(sections))

        # 3. Compress into page windows
        windows = compress_sections(sections)

        # 4. Split into scopes
        scopes = split_into_scopes(windows)
        if not scopes:
            raise ValueError("No processing scopes generated")

        # 5. Process each scope through AI Gateway (serial to respect rate limits)
        all_entries: list[dict] = []
        for i, scope in enumerate(scopes):
            logger.info(
                "processing_scope",
                index=i + 1,
                total=len(scopes),
                scope_type=scope.scope_type,
                chapter=scope.chapter_label,
            )

            prompt = build_prompt(scope)
            raw_response = _call_ai_gateway(conn, prompt, scope.chapter_label)
            entries = _parse_llm_json(raw_response)

            # Annotate entries with scope metadata
            for entry in entries:
                entry["clause_type"] = scope.scope_type
                if entry.get("page_start") is None:
                    entry["page_start"] = scope.page_start

            all_entries.extend(entries)

            # Rate limit: 2-second delay between scopes
            if i < len(scopes) - 1:
                time.sleep(2)

        logger.info("all_scopes_processed", total_entries=len(all_entries))

        # 6. Build tree, link commentary, validate
        clauses = build_tree(all_entries, standard_id)
        clauses = link_commentary(clauses)
        warnings = validate_tree(clauses)

        # 7. Delete old clauses and bulk insert new ones
        _std_repo.delete_clauses(conn, standard_id)
        inserted = _std_repo.bulk_create_clauses(conn, clauses)

        # 8. Index to OpenSearch
        standard = _std_repo.get_standard(conn, standard_id)
        _index_clauses(standard, clauses)

        # 9. Update status to completed
        _std_repo.update_processing_status(conn, standard_id, "completed")

        elapsed = time.time() - started_at
        summary = {
            "standard_id": str(standard_id),
            "status": "completed",
            "total_clauses": inserted,
            "normative": sum(1 for c in clauses if c["clause_type"] == "normative"),
            "commentary": sum(1 for c in clauses if c["clause_type"] == "commentary"),
            "scopes_processed": len(scopes),
            "warnings": warnings[:5],
            "elapsed_seconds": round(elapsed, 1),
        }
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
        docs = []
        for c in clauses:
            doc_id = str(c["id"])
            docs.append((doc_id, {
                "standard_id": str(standard["id"]),
                "standard_code": standard.get("standard_code"),
                "clause_id": doc_id,
                "clause_no": c.get("clause_no"),
                "clause_title": c.get("clause_title"),
                "clause_text": c.get("clause_text"),
                "summary": c.get("summary"),
                "tags": c.get("tags", []),
                "specialty": standard.get("specialty"),
            }))

        asyncio.get_event_loop().run_until_complete(
            manager.bulk_index("clause_index", docs)
        )
    except Exception:
        logger.warning("opensearch_indexing_failed", exc_info=True)
