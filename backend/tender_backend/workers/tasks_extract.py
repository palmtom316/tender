"""Celery tasks for trackable AI tender extraction."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import structlog

from tender_backend.core.config import get_settings
from tender_backend.db.pool import get_pool
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.db.repositories.tender_ai_extraction_repo import TenderAiExtractionRepository
from tender_backend.db.repositories.tender_document_repository import TenderDocumentRepository
from tender_backend.services.deepseek_api import DEEPSEEK_V4_MAX_REASONING_EFFORT, DEEPSEEK_V4_PRO_MODEL
from tender_backend.services.extract_service.ai_requirements_extractor import (
    build_batch_overrides,
    extract_requirements_for_batch,
    run_stage1_prefilter,
)
from tender_backend.services.extract_service.retry_policy import (
    backoff_countdown_seconds,
    degraded_reasoning_effort,
    pro_review_batch_index,
    provider_limit_for,
    retry_batch_index,
    should_create_retry_batches,
    split_chunk_ids_for_retry,
)
from tender_backend.workers.celery_app import app

logger = structlog.stdlib.get_logger(__name__)

_ai_repo = TenderAiExtractionRepository()
_doc_repo = TenderDocumentRepository()
_requirement_repo = RequirementRepository()

_HIGH_VALUE_REVIEW_KEYWORDS = (
    "否决",
    "废标",
    "无效投标",
    "不予受理",
    "实质性不响应",
    "投标无效",
    "资质",
    "资格",
    "评分",
    "评审",
    "递交",
    "技术要求",
    "技术规范",
    "投标文件组成",
)


def _run_async(coro):
    return asyncio.run(coro)


def _batch_metadata(batch: dict[str, Any]) -> dict[str, Any]:
    return dict(batch.get("metadata_json") or {})


def _batch_is_high_value(batch: dict[str, Any]) -> bool:
    metadata = _batch_metadata(batch)
    return bool(metadata.get("high_value"))


def _batch_quality_policy(batch: dict[str, Any]) -> str:
    return str(_batch_metadata(batch).get("quality_policy") or "legacy")


def _batch_thinking_enabled(batch: dict[str, Any]) -> bool | None:
    value = _batch_metadata(batch).get("thinking_enabled")
    if value is None:
        return None
    return bool(value)


def _quality_policy_priority(batch: dict[str, Any]) -> int:
    quality_policy = _batch_quality_policy(batch)
    if quality_policy == "pro_review":
        return 0
    if quality_policy == "table_or_critical_extract":
        return 1
    if quality_policy == "flash_extract":
        return 2
    if quality_policy == "fast_prefilter":
        return 3
    return 9


def _batch_has_review_keywords(chunks: list[dict[str, Any]]) -> bool:
    for chunk in chunks:
        text = " ".join(
            str(part or "")
            for part in (
                chunk.get("title"),
                chunk.get("section_title"),
                chunk.get("text"),
                chunk.get("source_file"),
            )
        )
        table = chunk.get("table_json") or {}
        if table.get("rows"):
            text = f"{text} {table['rows']}"
        if any(keyword in text for keyword in _HIGH_VALUE_REVIEW_KEYWORDS):
            return True
    return False


def _needs_review_for_empty_output(
    *,
    batch: dict[str, Any],
    chunks: list[dict[str, Any]],
    usage,
) -> bool:
    if usage is None or usage.failed or usage.extracted > 0:
        return False
    batch_quality = usage.batch_quality or {}
    empty_reason = str(batch_quality.get("empty_reason") or "").strip()
    if empty_reason in {"template_blank", "reference_only", "true_empty"}:
        return False
    return batch_quality.get("suspected_missing") is True


def _review_batch_already_created(batch: dict[str, Any]) -> bool:
    return bool(_batch_metadata(batch).get("review_of_batch_id"))


def _build_review_metadata(batch: dict[str, Any], usage) -> dict[str, Any]:
    metadata = _batch_metadata(batch)
    review_metadata = {
        **metadata,
        "task_type": str(metadata.get("task_type") or "extract_tender_requirements"),
        "review_of_batch_id": str(batch["id"]),
        "review_reason": "empty_high_value_output",
        "review_source_model": batch.get("model"),
        "review_source_reasoning_effort": batch.get("reasoning_effort"),
        "review_source_batch_quality": usage.batch_quality if usage else {},
    }
    review_metadata["high_value"] = True
    return review_metadata


def _build_retry_batches(batch: dict[str, Any], *, error_type: str, error_message: str) -> list[dict[str, Any]]:
    metadata = _batch_metadata(batch)
    chunk_id_groups = split_chunk_ids_for_retry(batch.get("chunk_ids_json") or [])
    if not chunk_id_groups:
        return []
    retry_effort = degraded_reasoning_effort(batch.get("reasoning_effort"))
    retry_batches: list[dict[str, Any]] = []
    total_chunks = max(1, int(batch.get("chunk_count") or len(batch.get("chunk_ids_json") or [])))
    total_chars = int(batch.get("input_char_count") or 0)
    total_tokens = int(batch.get("estimated_input_tokens") or 0)
    for part_index, chunk_ids in enumerate(chunk_id_groups):
        ratio = len(chunk_ids) / total_chunks
        retry_batches.append(
            {
                "tender_document_file_id": batch.get("tender_document_file_id"),
                "source_file": batch["source_file"],
                "batch_index": retry_batch_index(
                    batch_index=batch["batch_index"],
                    part_index=part_index,
                ),
                "chunk_ids": chunk_ids,
                "status": "pending",
                "chunk_count": len(chunk_ids),
                "input_char_count": max(1, int(total_chars * ratio)) if total_chars else 0,
                "estimated_input_tokens": max(1, int(total_tokens * ratio)) if total_tokens else 0,
                "model": batch.get("model"),
                "reasoning_effort": retry_effort,
                "response_format": batch.get("response_format", "json_object"),
                "max_retries": 1,
                "metadata_json": {
                    **metadata,
                    "task_type": str(metadata.get("task_type") or "extract_tender_requirements"),
                    "retry_of_batch_id": str(batch["id"]),
                    "retry_part_index": part_index,
                    "retry_part_count": len(chunk_id_groups),
                    "retry_reason": error_type,
                    "retry_error_message": error_message[:500],
                    "retry_source_model": batch.get("model"),
                    "retry_source_reasoning_effort": batch.get("reasoning_effort"),
                    "retry_strategy": "split_batch_and_degrade_effort",
                    "stage": "retry",
                },
            }
        )
    return retry_batches


def _handle_batch_failure(
    *,
    conn,
    batch: dict[str, Any],
    batch_uuid,
    batch_id: str,
    error_type: str,
    error_message: str,
) -> dict[str, Any]:
    retry_count = int(batch.get("retry_count") or 0)
    retryable = retry_count + 1 < int(batch.get("max_retries") or 0)
    if should_create_retry_batches(
        retry_count=retry_count,
        metadata=_batch_metadata(batch),
        error_type=error_type,
        error_message=error_message,
    ):
        retry_batches = _build_retry_batches(
            batch,
            error_type=error_type,
            error_message=error_message,
        )
        created_retry_batches = _ai_repo.create_retry_batches(
            conn,
            source_batch=batch,
            retry_batches=retry_batches,
        )
        _ai_repo.mark_batch_superseded(
            conn,
            batch_id=batch_uuid,
            metadata_json={
                **_batch_metadata(batch),
                "planned_model": batch.get("model"),
                "planned_reasoning_effort": batch.get("reasoning_effort"),
                "retry_batch_ids": [str(item["id"]) for item in created_retry_batches],
                "retry_reason": error_type,
                "retry_error_message": error_message[:500],
                "retry_strategy": "split_batch_and_degrade_effort",
            },
        )
        for retry_batch in created_retry_batches:
            run_tender_ai_extraction_batch.apply_async(
                kwargs={"batch_id": str(retry_batch["id"])},
                countdown=backoff_countdown_seconds(
                    retry_count=retry_count,
                    error_type=error_type,
                    error_message=error_message,
                ),
            )
        run = _ai_repo.refresh_run_progress(conn, run_id=batch["run_id"])
        conn.commit()
        return {"batch_id": batch_id, "run_status": run.get("status") if run else None}

    _ai_repo.mark_batch_failed(
        conn,
        batch_id=batch_uuid,
        error_type=error_type,
        error_message=error_message,
        retryable=retryable,
    )
    if retryable:
        countdown = backoff_countdown_seconds(
            retry_count=retry_count,
            error_type=error_type,
            error_message=error_message,
        )
        if countdown:
            run_tender_ai_extraction_batch.apply_async(
                kwargs={"batch_id": batch_id},
                countdown=countdown,
            )
    run = _ai_repo.refresh_run_progress(conn, run_id=batch["run_id"])
    conn.commit()
    return {"batch_id": batch_id, "run_status": run.get("status") if run else None}


def _dispatch_batch(batch: dict[str, Any]) -> bool:
    limit = provider_limit_for(
        model=batch.get("model"),
        reasoning_effort=batch.get("reasoning_effort"),
        thinking_enabled=_batch_thinking_enabled(batch),
        quality_policy=_batch_quality_policy(batch),
    )
    running = _ai_repo.count_running_batches_for_provider(
        batch["_conn"],
        model=limit.model,
        reasoning_effort=limit.reasoning_effort,
        thinking_enabled=limit.thinking_enabled,
        quality_policy=limit.quality_policy,
    )
    if running >= limit.max_running:
        countdown = 15
        run_tender_ai_extraction_batch.apply_async(
            kwargs={"batch_id": str(batch["id"])},
            countdown=countdown,
        )
        logger.info(
            "tender_ai_extraction_batch_deferred_provider_limit",
            batch_id=str(batch["id"]),
            model=limit.model,
            reasoning_effort=limit.reasoning_effort,
            running=running,
            max_running=limit.max_running,
            countdown=countdown,
        )
        return False
    run_tender_ai_extraction_batch.delay(batch_id=str(batch["id"]))
    return True


def _provider_limit_countdown(conn, batch: dict[str, Any]) -> int:
    limit = provider_limit_for(
        model=batch.get("model"),
        reasoning_effort=batch.get("reasoning_effort"),
        thinking_enabled=_batch_thinking_enabled(batch),
        quality_policy=_batch_quality_policy(batch),
    )
    running = _ai_repo.count_running_batches_for_provider(
        conn,
        model=limit.model,
        reasoning_effort=limit.reasoning_effort,
        thinking_enabled=limit.thinking_enabled,
        quality_policy=limit.quality_policy,
    )
    if running <= limit.max_running:
        return 0
    logger.info(
        "tender_ai_extraction_batch_requeued_provider_limit",
        batch_id=str(batch["id"]),
        model=limit.model,
        reasoning_effort=limit.reasoning_effort,
        running=running,
        max_running=limit.max_running,
    )
    return 15


def _resolve_batch_overrides(
    conn,
    *,
    batch: dict[str, Any],
) -> tuple[dict | None, dict | None]:
    metadata = _batch_metadata(batch)
    return build_batch_overrides(
        conn,
        model=batch.get("model"),
        thinking_enabled=metadata.get("thinking_enabled"),
        reasoning_effort=batch.get("reasoning_effort"),
    )


def _output_tokens_to_max_ratio(*, usage, batch: dict[str, Any]) -> float:
    if usage is None:
        return 0.0
    hint = int(
        _batch_metadata(batch).get("max_tokens_hint")
        or getattr(usage, "max_tokens_hint", 0)
        or 0
    )
    if hint <= 0:
        return 0.0
    return float(usage.output_tokens) / float(hint)


def _build_followup_batch_from_prefilter(
    *,
    batch: dict[str, Any],
    candidate_chunks: list[dict[str, Any]],
    prefilter_stats: dict[str, int],
) -> dict[str, Any] | None:
    if not candidate_chunks:
        return None
    metadata = _batch_metadata(batch)
    next_quality_policy = str(metadata.get("next_quality_policy") or "flash_extract")
    next_model = str(metadata.get("next_model") or "deepseek-v4-flash")
    next_reasoning_effort = metadata.get("next_reasoning_effort")
    chunk_ids = [str(chunk.get("id")) for chunk in candidate_chunks if chunk.get("id")]
    if not chunk_ids:
        return None
    return {
        "tender_document_file_id": batch.get("tender_document_file_id"),
        "source_file": batch["source_file"],
        "batch_index": int(batch["batch_index"]) + 50_000,
        "chunk_ids": chunk_ids,
        "status": "pending",
        "chunk_count": len(chunk_ids),
        "input_char_count": int(batch.get("input_char_count") or 0),
        "estimated_input_tokens": int(batch.get("estimated_input_tokens") or 0),
        "model": next_model,
        "reasoning_effort": next_reasoning_effort,
        "response_format": batch.get("response_format", "json_object"),
        "max_retries": 1,
        "metadata_json": {
            **metadata,
            "task_type": str(metadata.get("task_type") or "extract_tender_requirements"),
            "quality_policy": next_quality_policy,
            "thinking_enabled": False,
            "planned_thinking": "disabled",
            "prefilter_of_batch_id": str(batch["id"]),
            "prefilter_candidate_chunk_count": prefilter_stats.get("candidate_chunk_count", len(chunk_ids)),
            "prefilter_original_chunk_count": prefilter_stats.get("original_chunk_count", len(chunk_ids)),
            "prefilter_dropped_chunks": prefilter_stats.get("prefilter_dropped_chunks", 0),
            "stage": "followup",
        },
    }


@app.task(name="tender_backend.workers.tasks_extract.run_tender_ai_extraction", bind=True)
def run_tender_ai_extraction(self, *, run_id: str) -> dict:
    """Dispatch all pending batches for an extraction run."""
    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)
    run_uuid = UUID(run_id)
    dispatched = 0
    with pool.connection() as conn:
        run = _ai_repo.get_run(conn, run_id=run_uuid)
        if run is None:
            raise ValueError(f"tender ai extraction run not found: {run_id}")
        batches = _ai_repo.list_batches(conn, run_id=run_uuid, status="pending")
        batches.sort(
            key=lambda batch: (
                _quality_policy_priority(batch),
                str(batch.get("source_file") or ""),
                int(batch.get("batch_index") or 0),
            )
        )
        for batch in batches:
            batch["_conn"] = conn
            if _dispatch_batch(batch):
                dispatched += 1
        _ai_repo.refresh_run_progress(conn, run_id=run_uuid)
        conn.commit()
    logger.info("tender_ai_extraction_dispatched", run_id=run_id, dispatched=dispatched)
    return {"run_id": run_id, "dispatched": dispatched}


@app.task(name="tender_backend.workers.tasks_extract.run_tender_ai_extraction_batch", bind=True)
def run_tender_ai_extraction_batch(self, *, batch_id: str) -> dict:
    """Execute one preplanned AI extraction batch and persist its status."""
    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)
    batch_uuid = UUID(batch_id)
    with pool.connection() as conn:
        batch = _ai_repo.mark_batch_running(conn, batch_id=batch_uuid)
        if batch is None:
            existing = _ai_repo.get_batch(conn, batch_id=batch_uuid)
            return {"batch_id": batch_id, "status": existing.get("status") if existing else "missing"}
        queue_to_start_ms = 0
        created_at = batch.get("created_at")
        started_at = batch.get("started_at")
        if created_at is not None and started_at is not None:
            queue_to_start_ms = max(0, int((started_at - created_at).total_seconds() * 1000))
        provider_limit_countdown = _provider_limit_countdown(conn, batch)
        if provider_limit_countdown:
            _ai_repo.defer_batch(
                conn,
                batch_id=batch_uuid,
                error_type="ProviderConcurrencyLimit",
                error_message="provider concurrency limit reached; requeued",
            )
            conn.commit()
            run_tender_ai_extraction_batch.apply_async(
                kwargs={"batch_id": batch_id},
                countdown=provider_limit_countdown,
            )
            return {"batch_id": batch_id, "status": "requeued_provider_limit"}
        run = _ai_repo.get_run(conn, run_id=batch["run_id"])
        if run is None:
            raise ValueError(f"tender ai extraction run not found: {batch['run_id']}")
        chunk_ids = {str(value) for value in (batch.get("chunk_ids_json") or [])}
        chunks = [
            chunk for chunk in _doc_repo.list_source_chunks(
                conn, tender_document_id=batch["tender_document_id"]
            )
            if str(chunk.get("id")) in chunk_ids
        ]
        chunks.sort(key=lambda c: (c.get("sort_order") or 0, str(c.get("id") or "")))
        primary_override, fallback_override = _resolve_batch_overrides(conn, batch=batch)
        conn.commit()

    persisted: list[dict] = []

    async def _persist(batch_requirements):
        if not batch_requirements:
            return
        persist_started = asyncio.get_running_loop().time()
        payload = [item.to_repository_dict() for item in batch_requirements]
        with pool.connection() as persist_conn:
            rows = _requirement_repo.create_many(
                persist_conn,
                project_id=run["project_id"],
                requirements=payload,
            )
        persisted.extend(rows)
        persist_elapsed_ms = int((asyncio.get_running_loop().time() - persist_started) * 1000)
        batch.setdefault("_persist_latency_ms", 0)
        batch["_persist_latency_ms"] = max(batch["_persist_latency_ms"], persist_elapsed_ms)

    try:
        if _batch_quality_policy(batch) == "fast_prefilter":
            candidate_chunks, prefilter_stats = run_stage1_prefilter(
                chunks,
                quality_policy="flash_extract",
            )
            with pool.connection() as conn:
                followup_payload = _build_followup_batch_from_prefilter(
                    batch=batch,
                    candidate_chunks=candidate_chunks,
                    prefilter_stats=prefilter_stats,
                )
                followup_batch = None
                if followup_payload is not None:
                    created = _ai_repo.create_retry_batches(
                        conn,
                        source_batch=batch,
                        retry_batches=[followup_payload],
                    )
                    followup_batch = created[0] if created else None
                _ai_repo.mark_batch_succeeded(
                    conn,
                    batch_id=batch_uuid,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=0,
                    extracted_requirements=0,
                    dropped_invalid=0,
                    metadata_json={
                        **_batch_metadata(batch),
                        "task_type": str(_batch_metadata(batch).get("task_type") or "extract_tender_requirements"),
                        "strategy_version": _batch_metadata(batch).get("strategy_version"),
                        "quality_policy": _batch_quality_policy(batch),
                        "thinking_enabled": _batch_metadata(batch).get("thinking_enabled"),
                        "queue_to_start_ms": queue_to_start_ms,
                        "provider_latency_ms": 0,
                        "persist_latency_ms": 0,
                        "prompt_cache_hit_ratio": 0.0,
                        "original_chunk_count": prefilter_stats.get("original_chunk_count", 0),
                        "candidate_chunk_count": prefilter_stats.get("candidate_chunk_count", 0),
                        "prefilter_dropped_chunks": prefilter_stats.get("prefilter_dropped_chunks", 0),
                        "prefilter_batch_completed": True,
                        "followup_batch_id": str(followup_batch["id"]) if followup_batch else None,
                    },
                )
                run = _ai_repo.refresh_run_progress(conn, run_id=batch["run_id"])
                conn.commit()
            if followup_batch is not None:
                run_tender_ai_extraction_batch.apply_async(
                    kwargs={"batch_id": str(followup_batch["id"])},
                    countdown=1,
                )
            return {"batch_id": batch_id, "run_status": run.get("status") if run else None}

        if primary_override is None and fallback_override is None:
            with pool.connection() as extract_conn:
                summary = _run_async(
                    extract_requirements_for_batch(
                        chunks,
                        conn=extract_conn,
                        source_file=batch["source_file"],
                        primary_override=primary_override,
                        fallback_override=fallback_override,
                        response_format=batch.get("response_format") or "json_object",
                        stream=True,
                        quality_policy=_batch_quality_policy(batch),
                        on_batch_persisted=_persist,
                    )
                )
        else:
            summary = _run_async(
                extract_requirements_for_batch(
                    chunks,
                    source_file=batch["source_file"],
                    primary_override=primary_override,
                    fallback_override=fallback_override,
                    response_format=batch.get("response_format") or "json_object",
                    stream=True,
                    quality_policy=_batch_quality_policy(batch),
                    on_batch_persisted=_persist,
                )
            )
        with pool.connection() as conn:
            usage = summary.batches[0] if summary.batches else None
            if usage is not None and usage.failed:
                return _handle_batch_failure(
                    conn=conn,
                    batch=batch,
                    batch_uuid=batch_uuid,
                    batch_id=batch_id,
                    error_type=usage.error_type or "AiExtractionError",
                    error_message=usage.error_message or usage.error_type or "AI extraction batch failed",
                )
            elif _needs_review_for_empty_output(batch=batch, chunks=chunks, usage=usage):
                if _review_batch_already_created(batch):
                    _ai_repo.mark_batch_failed(
                        conn,
                        batch_id=batch_uuid,
                        error_type="EmptyHighValueOutput",
                        error_message="pro review batch returned zero requirements and requires review",
                        retryable=False,
                    )
                else:
                    review_batch = _ai_repo.create_review_batch(
                        conn,
                        source_batch=batch,
                        batch_index=pro_review_batch_index(batch["batch_index"]),
                        model=DEEPSEEK_V4_PRO_MODEL,
                        reasoning_effort=DEEPSEEK_V4_MAX_REASONING_EFFORT,
                        metadata_json=_build_review_metadata(batch, usage),
                    )
                    _ai_repo.mark_batch_succeeded(
                        conn,
                        batch_id=batch_uuid,
                        input_tokens=summary.total_input_tokens,
                        output_tokens=summary.total_output_tokens,
                        latency_ms=usage.latency_ms if usage else 0,
                        extracted_requirements=0,
                        dropped_invalid=usage.dropped_invalid if usage else 0,
                        metadata_json={
                            **_batch_metadata(batch),
                            "planned_model": batch.get("model"),
                            "planned_reasoning_effort": batch.get("reasoning_effort"),
                            "actual_model": usage.resolved_model if usage else None,
                            "actual_reasoning_effort": batch.get("reasoning_effort"),
                            "used_fallback": usage.used_fallback if usage else False,
                            "finish_reason": usage.finish_reason if usage else None,
                            "prompt_cache_hit_tokens": usage.prompt_cache_hit_tokens if usage else 0,
                            "prompt_cache_miss_tokens": usage.prompt_cache_miss_tokens if usage else 0,
                            "reasoning_tokens": usage.reasoning_tokens if usage else 0,
                            "batch_quality": usage.batch_quality if usage else {},
                            "strategy_version": _batch_metadata(batch).get("strategy_version"),
                            "quality_policy": _batch_quality_policy(batch),
                            "thinking_enabled": _batch_metadata(batch).get("thinking_enabled"),
                            "queue_to_start_ms": queue_to_start_ms,
                            "provider_latency_ms": usage.latency_ms if usage else 0,
                            "persist_latency_ms": int(batch.get("_persist_latency_ms") or 0),
                            "prompt_cache_hit_ratio": usage.prompt_cache_hit_ratio if usage else 0.0,
                            "original_chunk_count": usage.original_chunk_count if usage else 0,
                            "candidate_chunk_count": usage.candidate_chunk_count if usage else 0,
                            "prefilter_dropped_chunks": usage.prefilter_dropped_chunks if usage else 0,
                            "max_tokens_hint": usage.max_tokens_hint if usage else 0,
                            "output_tokens_to_max_ratio": _output_tokens_to_max_ratio(usage=usage, batch=batch),
                            "review_batch_id": str(review_batch["id"]) if review_batch else None,
                            "review_reason": "empty_high_value_output",
                        },
                    )
                    if review_batch is not None:
                        run_tender_ai_extraction_batch.apply_async(
                            kwargs={"batch_id": str(review_batch["id"])},
                            countdown=5,
                        )
            else:
                _ai_repo.mark_batch_succeeded(
                    conn,
                    batch_id=batch_uuid,
                    input_tokens=summary.total_input_tokens,
                    output_tokens=summary.total_output_tokens,
                    latency_ms=usage.latency_ms if usage else 0,
                        extracted_requirements=len(persisted),
                        dropped_invalid=usage.dropped_invalid if usage else 0,
                        metadata_json={
                            **_batch_metadata(batch),
                            "planned_model": batch.get("model"),
                            "planned_reasoning_effort": batch.get("reasoning_effort"),
                            "actual_model": usage.resolved_model if usage else None,
                        "actual_reasoning_effort": batch.get("reasoning_effort"),
                        "used_fallback": usage.used_fallback if usage else False,
                        "finish_reason": usage.finish_reason if usage else None,
                        "prompt_cache_hit_tokens": usage.prompt_cache_hit_tokens if usage else 0,
                        "prompt_cache_miss_tokens": usage.prompt_cache_miss_tokens if usage else 0,
                        "reasoning_tokens": usage.reasoning_tokens if usage else 0,
                        "batch_quality": usage.batch_quality if usage else {},
                        "strategy_version": _batch_metadata(batch).get("strategy_version"),
                        "quality_policy": _batch_quality_policy(batch),
                        "thinking_enabled": _batch_metadata(batch).get("thinking_enabled"),
                        "queue_to_start_ms": queue_to_start_ms,
                        "provider_latency_ms": usage.latency_ms if usage else 0,
                        "persist_latency_ms": int(batch.get("_persist_latency_ms") or 0),
                        "prompt_cache_hit_ratio": usage.prompt_cache_hit_ratio if usage else 0.0,
                        "original_chunk_count": usage.original_chunk_count if usage else 0,
                        "candidate_chunk_count": usage.candidate_chunk_count if usage else 0,
                        "prefilter_dropped_chunks": usage.prefilter_dropped_chunks if usage else 0,
                        "max_tokens_hint": usage.max_tokens_hint if usage else 0,
                        "output_tokens_to_max_ratio": _output_tokens_to_max_ratio(usage=usage, batch=batch),
                    },
                )
            run = _ai_repo.refresh_run_progress(conn, run_id=batch["run_id"])
            conn.commit()
    except Exception as exc:
        with pool.connection() as conn:
            logger.exception("tender_ai_extraction_batch_failed", batch_id=batch_id)
            return _handle_batch_failure(
                conn=conn,
                batch=batch,
                batch_uuid=batch_uuid,
                batch_id=batch_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
    return {"batch_id": batch_id, "run_status": run.get("status") if run else None}


@app.task(name="tender_backend.workers.tasks_extract.retry_failed_tender_ai_extraction_batches", bind=True)
def retry_failed_tender_ai_extraction_batches(self, *, run_id: str) -> dict:
    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)
    run_uuid = UUID(run_id)
    with pool.connection() as conn:
        reset_count = _ai_repo.reset_failed_batches(conn, run_id=run_uuid)
        conn.commit()
    if reset_count:
        run_tender_ai_extraction.delay(run_id=run_id)
    return {"run_id": run_id, "reset_batches": reset_count}
