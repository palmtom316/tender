"""Retry and provider concurrency policy for tender AI extraction."""

from __future__ import annotations

import random
from dataclasses import dataclass

from tender_backend.services.deepseek_api import (
    DEEPSEEK_V4_FLASH_MODEL,
    DEEPSEEK_V4_MAX_REASONING_EFFORT,
    DEEPSEEK_V4_PRO_MODEL,
)


@dataclass(frozen=True)
class ProviderLimit:
    model: str
    reasoning_effort: str | None
    max_running: int


PRO_REVIEW_BATCH_INDEX_OFFSET = 10_000
RETRY_BATCH_INDEX_OFFSET = 20_000
MAX_RETRY_SPLIT_PARTS = 4


def provider_limit_for(*, model: str | None, reasoning_effort: str | None) -> ProviderLimit:
    normalized_model = (model or DEEPSEEK_V4_FLASH_MODEL).strip()
    normalized_effort = (reasoning_effort or "").strip() or None
    if normalized_model == DEEPSEEK_V4_PRO_MODEL and normalized_effort == DEEPSEEK_V4_MAX_REASONING_EFFORT:
        return ProviderLimit(normalized_model, normalized_effort, 1)
    if normalized_model == DEEPSEEK_V4_PRO_MODEL:
        return ProviderLimit(normalized_model, normalized_effort, 2)
    if normalized_model == DEEPSEEK_V4_FLASH_MODEL:
        return ProviderLimit(normalized_model, normalized_effort, 4)
    return ProviderLimit(normalized_model, normalized_effort, 2)


def is_rate_or_transport_error(error_type: str | None, error_message: str | None = None) -> bool:
    combined = f"{error_type or ''} {error_message or ''}".lower()
    return any(
        marker in combined
        for marker in (
            "429",
            "rate",
            "ratelimit",
            "too many requests",
            "readerror",
            "readtimeout",
            "timeout",
            "connecterror",
            "bad gateway",
            "502",
            "broken pipe",
        )
    )


def backoff_countdown_seconds(*, retry_count: int, error_type: str | None, error_message: str | None = None) -> int:
    if not is_rate_or_transport_error(error_type, error_message):
        return 0
    capped_retry = max(0, min(int(retry_count), 6))
    base = min(300, 15 * (2**capped_retry))
    jitter = random.randint(0, min(30, base))
    return base + jitter


def pro_review_batch_index(batch_index: int) -> int:
    return PRO_REVIEW_BATCH_INDEX_OFFSET + int(batch_index)


def retry_batch_index(*, batch_index: int, part_index: int) -> int:
    return RETRY_BATCH_INDEX_OFFSET + int(batch_index) * 100 + int(part_index)


def degraded_reasoning_effort(reasoning_effort: str | None) -> str | None:
    normalized = (reasoning_effort or "").strip() or None
    if normalized == DEEPSEEK_V4_MAX_REASONING_EFFORT:
        return "high"
    if normalized == "high":
        return None
    return normalized


def split_chunk_ids_for_retry(chunk_ids: list[str], *, max_parts: int = MAX_RETRY_SPLIT_PARTS) -> list[list[str]]:
    ids = [str(value) for value in chunk_ids if value]
    if len(ids) <= 1:
        return [ids] if ids else []
    part_count = min(max_parts, max(2, len(ids)))
    part_size = (len(ids) + part_count - 1) // part_count
    return [ids[index : index + part_size] for index in range(0, len(ids), part_size)]


def should_create_retry_batches(*, retry_count: int, metadata: dict, error_type: str | None, error_message: str | None = None) -> bool:
    if int(retry_count or 0) > 0:
        return False
    if metadata.get("retry_of_batch_id") or metadata.get("review_of_batch_id"):
        return False
    return is_rate_or_transport_error(error_type, error_message)
