"""Run local VL repair tasks against rendered PDF page ranges."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from psycopg import Connection

from tender_backend.core.config import get_settings
from tender_backend.services.norm_service.repair_tasks import RepairTask
from tender_backend.services.vision_service.pdf_renderer import render_pdf_page_range
from tender_backend.services.vision_service.repair_prompt import build_repair_messages

logger = structlog.stdlib.get_logger(__name__)

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:8001")
_MAX_REPAIR_MODEL_ATTEMPTS = 3
_RETRYABLE_REPAIR_STATUS_CODES = {502, 503, 504}


def _repair_retry_backoff_seconds(attempt: int) -> float:
    return float(2 ** max(0, attempt - 1))


@dataclass(slots=True)
class RepairPatch:
    task_type: str
    source_ref: str
    status: str
    patched_text: str | None = None
    patched_table_html: str | None = None
    notes: str | None = None


def _get_pdf_path(conn: Connection, document_id: str) -> str | None:
    from tender_backend.services.norm_service.norm_processor import _get_pdf_path as _resolve_pdf_path

    return _resolve_pdf_path(conn, document_id)


def _ai_gateway_chat_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api"):
        return f"{normalized}/ai/chat"
    return f"{normalized}/api/ai/chat"


def _parse_patch(raw: str, task: RepairTask) -> RepairPatch:
    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    payload: dict[str, Any] = {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            payload = parsed
    except json.JSONDecodeError:
        logger.warning("repair_json_parse_failed", task_type=task.task_type, source_ref=task.source_ref)

    return RepairPatch(
        task_type=str(payload.get("task_type") or task.task_type),
        source_ref=str(payload.get("source_ref") or task.source_ref),
        status=str(payload.get("status") or "noop"),
        patched_text=payload.get("patched_text"),
        patched_table_html=payload.get("patched_table_html"),
        notes=payload.get("notes"),
    )


def _is_retryable_repair_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_REPAIR_STATUS_CODES
    return False


def _call_repair_model(conn: Connection, task: RepairTask, document_id: str) -> RepairPatch:
    settings = get_settings()
    if task.page_start is None:
        raise ValueError(f"Repair task {task.source_ref} is missing page_start")

    pdf_path = _get_pdf_path(conn, document_id)
    if not pdf_path:
        raise FileNotFoundError(f"PDF not found for document {document_id}")

    pages = render_pdf_page_range(
        pdf_path,
        page_start=task.page_start,
        page_end=task.page_end,
        dpi=settings.vl_repair_page_dpi,
    )
    messages = build_repair_messages(task, pages)

    payload: dict[str, Any] = {
        "task_type": "vision_repair",
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 4096,
    }

    for attempt in range(1, _MAX_REPAIR_MODEL_ATTEMPTS + 1):
        try:
            response = httpx.post(
                _ai_gateway_chat_url(AI_GATEWAY_URL),
                json=payload,
                timeout=settings.vl_repair_ai_gateway_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return _parse_patch(str(data.get("content") or ""), task)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            if not _is_retryable_repair_error(exc) or attempt >= _MAX_REPAIR_MODEL_ATTEMPTS:
                raise
            logger.warning(
                "repair_model_retrying",
                task_type=task.task_type,
                source_ref=task.source_ref,
                attempt=attempt,
                max_attempts=_MAX_REPAIR_MODEL_ATTEMPTS,
                error=str(exc),
            )
            time.sleep(_repair_retry_backoff_seconds(attempt))

    raise RuntimeError("unreachable")


def run_repair_tasks(*, conn: Connection, document_id: str, tasks: list[RepairTask]) -> list[RepairPatch]:
    """Execute local VL repair tasks serially."""
    patches: list[RepairPatch] = []
    for task in tasks:
        patches.append(_call_repair_model(conn, task, document_id))
    return patches
