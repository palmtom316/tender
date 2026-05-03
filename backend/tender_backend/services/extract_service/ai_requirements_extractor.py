"""AI-powered tender requirement extraction.

Calls the AI Gateway (`task_type=extract_tender_requirements`) to convert
parsed source chunks into structured project_requirement candidates with
traceable locators.

Strategy: each source_file is sent in its own AI call (split into sub-batches
when > 200 chunks).  Calls run concurrently with a bounded semaphore (4 by
default).  The `return_exceptions=True` gather + `on_batch_persisted`
checkpoint guarantee partial results even when a batch or the process fails.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
import structlog
from psycopg import Connection

from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository
from tender_backend.services.deepseek_api import (
    DEEPSEEK_V4_MAX_REASONING_EFFORT,
    DEEPSEEK_V4_PRO_MODEL,
    is_deepseek_v4_model,
)
from tender_backend.services.extract_service.requirements_extractor import (
    HARD_CONSTRAINT_CATEGORIES,
    HUMAN_CONFIRM_CATEGORIES,
    REQUIREMENT_CATEGORIES,
)

logger = structlog.stdlib.get_logger(__name__)

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:8100")

_MAX_CHUNKS_PER_BATCH = 200
_REQUEST_TIMEOUT_SECONDS = 2400.0
_DEFAULT_CONCURRENCY = 4

_VALID_CATEGORIES = set(REQUIREMENT_CATEGORIES)

_SYSTEM_PROMPT = (
    "你是招标文件解析专家。从给定的招标文件 source chunks 中识别"
    "对投标人有约束力的条款，按结构化 schema 输出 JSON。\n"
    "只输出 JSON 数组，不要任何解释、Markdown 围栏或前后缀。"
)

_INSTRUCTION = """\
任务：从下方 source_chunks 数组中抽取投标文件编写约束。

本批次来自文件：{source_file}（共 {chunk_count} 个 chunk）。请逐一检查每个 chunk。

判定规则：
- 抽取所有"对投标人提出明确要求/限制"的条款（资格、业绩、人员、技术、商务、格式、合同、特殊要求、否决条款等）。
- 招标人的内部说明、目录、纯页眉页脚不抽取。
- 报价/定价类信息标 ignored_for_pricing=true，仍可输出。
- 凡含"否决/废标/无效投标/不予受理/实质性不响应/投标无效"的，is_veto=true。
- 严格使用以下 category 之一：{categories}。
- 输出条款的 source_chunk_id 必须是输入数组里出现过的 id；不准虚构。
- 一个 chunk 可对应 0~N 条 requirement；同一条款不要重复输出。

输出 JSON 数组，每条字段：
{{
  "source_chunk_id": "<输入数组里的 id 字符串>",
  "category": "<上述 12 个 category 之一>",
  "title": "<≤80 字的简短标题，应概括该条款的核心要求>",
  "requirement_text": "<≤500 字的精炼条款，可对原文进行概括但不要丢失关键数字/资质名/期限>",
  "is_veto": <bool>,
  "is_hard_constraint": <bool>,
  "ignored_for_pricing": <bool>,
  "confidence": <0~1 的浮点数>
}}

source_chunks (JSON)：
{payload}
"""


@dataclass
class AiExtractedRequirement:
    category: str
    title: str
    requirement_text: str
    source_chunk_id: str
    source_file: str | None
    source_locator: str | None
    page_start: int | None
    paragraph_index: int | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    confidence: float
    is_veto: bool
    is_hard_constraint: bool
    requires_human_confirm: bool
    ignored_for_pricing: bool
    extraction_method: str = "ai"
    source_metadata: dict[str, Any] | None = None

    def to_repository_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "title": self.title,
            "requirement_text": self.requirement_text,
            "source_text": self.requirement_text,
            "source_file": self.source_file,
            "source_locator": self.source_locator,
            "confidence": self.confidence,
            "is_veto": self.is_veto,
            "requires_human_confirm": self.requires_human_confirm,
            "ignored_for_pricing": self.ignored_for_pricing,
            "is_hard_constraint": self.is_hard_constraint,
            "source_chunk_id": self.source_chunk_id,
            "source_metadata": self.source_metadata or {},
            "extraction_method": self.extraction_method,
        }


class AiExtractionError(RuntimeError):
    """Raised when the AI call or response cannot be processed."""


def _serialize_chunk_for_prompt(chunk: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(chunk["id"]),
        "chunk_type": chunk.get("chunk_type"),
        "source_locator": chunk.get("source_locator"),
        "title": chunk.get("title"),
    }
    text = (chunk.get("text") or "").strip()
    if text:
        payload["text"] = text
    table = chunk.get("table_json") or {}
    if table.get("rows"):
        payload["table_rows"] = table["rows"]
    return payload


def _group_chunks_by_file(chunks: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        sf = chunk.get("source_file") or "unknown"
        groups.setdefault(sf, []).append(chunk)
    for sf, items in groups.items():
        items.sort(key=lambda c: (c.get("sort_order") or 0))
    return list(groups.items())


def _split_into_batches(chunks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for chunk in chunks:
        if current and len(current) >= _MAX_CHUNKS_PER_BATCH:
            batches.append(current)
            current = []
        current.append(chunk)
    if current:
        batches.append(current)
    return batches


def _build_prompt(batch: list[dict[str, Any]], source_file: str) -> str:
    payload = json.dumps(
        [_serialize_chunk_for_prompt(c) for c in batch],
        ensure_ascii=False,
    )
    return _INSTRUCTION.format(
        categories=", ".join(sorted(_VALID_CATEGORIES)),
        source_file=source_file.split("/")[-1] if "/" in source_file else source_file,
        chunk_count=len(batch),
        payload=payload,
    )


def _ai_gateway_chat_url() -> str:
    return f"{AI_GATEWAY_URL.rstrip('/')}/api/ai/chat"


def _build_overrides(conn: Connection) -> tuple[dict | None, dict | None]:
    config = AgentConfigRepository().get_by_key(conn, "extract")
    if not config or not config.enabled:
        return None, None

    primary = None
    if config.base_url and config.api_key:
        primary_model = config.primary_model or DEEPSEEK_V4_PRO_MODEL
        primary = {
            "base_url": config.base_url,
            "api_key": config.api_key,
            "model": primary_model,
        }
        if is_deepseek_v4_model(primary_model):
            primary["extra_body"] = {"reasoning_effort": DEEPSEEK_V4_MAX_REASONING_EFFORT}

    fallback = None
    if config.fallback_base_url and config.fallback_api_key:
        fallback_model = config.fallback_model or "deepseek-v4-flash"
        fallback = {
            "base_url": config.fallback_base_url,
            "api_key": config.fallback_api_key,
            "model": fallback_model,
        }
        if is_deepseek_v4_model(fallback_model):
            fallback["extra_body"] = {"reasoning_effort": DEEPSEEK_V4_MAX_REASONING_EFFORT}

    return primary, fallback


async def _call_ai_gateway(
    client: httpx.AsyncClient,
    *,
    prompt: str,
    primary_override: dict | None,
    fallback_override: dict | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_type": "extract_tender_requirements",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }
    if primary_override:
        payload["primary_override"] = primary_override
    if fallback_override:
        payload["fallback_override"] = fallback_override
    if response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}

    resp = await client.post(
        _ai_gateway_chat_url(),
        json=payload,
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_llm_json_array(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        lines = [line for line in text.split("\n") if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "[":
                continue
            try:
                result, _end = decoder.raw_decode(text[index:])
                break
            except json.JSONDecodeError:
                continue
        else:
            logger.warning("ai_extract_json_unparseable", raw_length=len(text))
            return []
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []


def _normalize_requirement(
    item: dict[str, Any],
    chunk_index: dict[str, dict[str, Any]],
) -> AiExtractedRequirement | None:
    chunk_id = str(item.get("source_chunk_id") or "").strip()
    if not chunk_id:
        return None
    source_chunk = chunk_index.get(chunk_id)
    if source_chunk is None:
        return None

    category = str(item.get("category") or "").strip()
    if category not in _VALID_CATEGORIES:
        return None

    title = str(item.get("title") or "").strip()[:200]
    if not title:
        return None

    requirement_text = str(item.get("requirement_text") or "").strip()
    if not requirement_text:
        requirement_text = title

    is_veto = bool(item.get("is_veto", category == "veto"))
    is_hard_constraint = bool(
        item.get("is_hard_constraint", is_veto or category in HARD_CONSTRAINT_CATEGORIES)
    )
    ignored_for_pricing = bool(item.get("ignored_for_pricing", False))
    confidence_raw = item.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else 0.85
    except (TypeError, ValueError):
        confidence = 0.85
    confidence = max(0.0, min(1.0, confidence))

    requires_human_confirm = (
        is_veto or category in HUMAN_CONFIRM_CATEGORIES or confidence < 0.8
    )

    return AiExtractedRequirement(
        category=category,
        title=title,
        requirement_text=requirement_text[:1200],
        source_chunk_id=chunk_id,
        source_file=source_chunk.get("source_file"),
        source_locator=source_chunk.get("source_locator"),
        page_start=source_chunk.get("page_start"),
        paragraph_index=source_chunk.get("paragraph_index"),
        sheet_name=source_chunk.get("sheet_name"),
        row_start=source_chunk.get("row_start"),
        row_end=source_chunk.get("row_end"),
        confidence=confidence,
        is_veto=is_veto,
        is_hard_constraint=is_hard_constraint,
        requires_human_confirm=requires_human_confirm,
        ignored_for_pricing=ignored_for_pricing,
        source_metadata={
            "ai_resolved_model": item.get("_resolved_model"),
            "ai_used_fallback": item.get("_used_fallback", False),
            "ai_input_tokens": item.get("_input_tokens"),
            "ai_output_tokens": item.get("_output_tokens"),
            "chunk_type": source_chunk.get("chunk_type"),
        },
    )


@dataclass
class BatchUsage:
    source_file: str
    chunks_in_batch: int
    extracted: int
    dropped_invalid: int
    input_tokens: int
    output_tokens: int
    used_fallback: bool
    resolved_model: str
    latency_ms: int
    failed: bool = False
    error_type: str | None = None


@dataclass
class _BatchResult:
    usage: BatchUsage
    requirements: list[AiExtractedRequirement]


@dataclass
class AiExtractionRunSummary:
    requirements: list[AiExtractedRequirement]
    batches: list[BatchUsage]

    @property
    def total_input_tokens(self) -> int:
        return sum(b.input_tokens for b in self.batches)

    @property
    def total_output_tokens(self) -> int:
        return sum(b.output_tokens for b in self.batches)


async def _process_batch(
    client: httpx.AsyncClient,
    *,
    source_file: str,
    batch: list[dict[str, Any]],
    chunk_index: dict[str, dict[str, Any]],
    primary_override: dict | None,
    fallback_override: dict | None,
    response_format: str | None,
    seen_keys: set[tuple[str, str]],
    seen_lock: asyncio.Lock,
    on_batch_persisted: Callable[[list["AiExtractedRequirement"]], Awaitable[None]] | None,
) -> _BatchResult:
    prompt = _build_prompt(batch, source_file)
    try:
        response = await _call_ai_gateway(
            client, prompt=prompt, primary_override=primary_override,
            fallback_override=fallback_override, response_format=response_format,
        )
    except Exception as exc:
        logger.exception(
            "ai_extract_batch_failed",
            source_file=source_file, batch_size=len(batch),
            error_type=type(exc).__name__,
        )
        return _BatchResult(
            usage=BatchUsage(source_file=source_file, chunks_in_batch=len(batch),
                             extracted=0, dropped_invalid=0, input_tokens=0,
                             output_tokens=0, used_fallback=False,
                             resolved_model="", latency_ms=0,
                             failed=True, error_type=type(exc).__name__),
            requirements=[],
        )

    content = response.get("content") or ""
    parsed_items = _parse_llm_json_array(content)
    requirements: list[AiExtractedRequirement] = []
    dropped_in_batch = 0

    for item in parsed_items:
        item.setdefault("_resolved_model", response.get("resolved_model"))
        item.setdefault("_used_fallback", response.get("used_fallback", False))
        item.setdefault("_input_tokens", response.get("input_tokens"))
        item.setdefault("_output_tokens", response.get("output_tokens"))
        normalized = _normalize_requirement(item, chunk_index)
        if normalized is None:
            dropped_in_batch += 1
            continue
        dedupe_key = (normalized.category, normalized.source_chunk_id)
        async with seen_lock:
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
        requirements.append(normalized)

    usage = BatchUsage(
        source_file=source_file, chunks_in_batch=len(batch),
        extracted=len(requirements), dropped_invalid=dropped_in_batch,
        input_tokens=int(response.get("input_tokens") or 0),
        output_tokens=int(response.get("output_tokens") or 0),
        used_fallback=bool(response.get("used_fallback", False)),
        resolved_model=str(response.get("resolved_model") or ""),
        latency_ms=int(response.get("latency_ms") or 0),
    )
    logger.info(
        "ai_extract_batch_done",
        source_file=source_file, chunks_in_batch=len(batch),
        extracted=usage.extracted, dropped=dropped_in_batch,
        resolved_model=usage.resolved_model,
        input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
    )
    if on_batch_persisted is not None and requirements:
        try:
            await on_batch_persisted(requirements)
        except Exception:
            logger.exception("ai_extract_batch_persist_failed",
                             source_file=source_file, count=len(requirements))
    return _BatchResult(usage=usage, requirements=requirements)


async def extract_requirements_with_ai(
    chunks: list[dict[str, Any]],
    *,
    conn: Connection,
    concurrency: int = _DEFAULT_CONCURRENCY,
    response_format: str | None = "json_object",
    on_batch_persisted: Callable[[list[AiExtractedRequirement]], Awaitable[None]] | None = None,
) -> AiExtractionRunSummary:
    """Run AI extraction — one batch per source_file, concurrent, with checkpoints."""
    chunk_index = {str(c["id"]): c for c in chunks if c.get("id") is not None}
    primary_override, fallback_override = _build_overrides(conn)

    plan: list[tuple[str, list[dict[str, Any]]]] = []
    for source_file, file_chunks in _group_chunks_by_file(chunks):
        usable = [
            c for c in file_chunks
            if (c.get("text") or "").strip() or (c.get("table_json") or {}).get("rows")
        ]
        if not usable:
            continue
        for batch in _split_into_batches(usable):
            plan.append((source_file, batch))

    if not plan:
        return AiExtractionRunSummary(requirements=[], batches=[])

    semaphore = asyncio.Semaphore(max(1, concurrency))
    seen_keys: set[tuple[str, str]] = set()
    seen_lock = asyncio.Lock()

    async with httpx.AsyncClient() as client:
        async def _runner(sf: str, b: list[dict[str, Any]]) -> _BatchResult:
            async with semaphore:
                return await _process_batch(
                    client, source_file=sf, batch=b,
                    chunk_index=chunk_index,
                    primary_override=primary_override,
                    fallback_override=fallback_override,
                    response_format=response_format,
                    seen_keys=seen_keys, seen_lock=seen_lock,
                    on_batch_persisted=on_batch_persisted,
                )

        results = await asyncio.gather(
            *(_runner(sf, b) for sf, b in plan),
            return_exceptions=True,
        )

    all_requirements: list[AiExtractedRequirement] = []
    all_batches: list[BatchUsage] = []
    for result in results:
        if isinstance(result, _BatchResult):
            all_batches.append(result.usage)
            all_requirements.extend(result.requirements)
        else:
            logger.warning("ai_extract_gather_exception", error=str(result))

    return AiExtractionRunSummary(requirements=all_requirements, batches=all_batches)


async def extract_requirements_for_batch(
    chunks: list[dict[str, Any]],
    *,
    conn: Connection,
    source_file: str,
    response_format: str | None = "json_object",
    on_batch_persisted: Callable[[list[AiExtractedRequirement]], Awaitable[None]] | None = None,
) -> AiExtractionRunSummary:
    """Run AI extraction for a preplanned batch.

    The caller owns batch status and retry behavior. This function keeps the
    model call and normalization logic shared with the legacy full-run helper.
    """
    chunk_index = {str(c["id"]): c for c in chunks if c.get("id") is not None}
    primary_override, fallback_override = _build_overrides(conn)
    seen_keys: set[tuple[str, str]] = set()
    seen_lock = asyncio.Lock()
    async with httpx.AsyncClient() as client:
        result = await _process_batch(
            client,
            source_file=source_file,
            batch=chunks,
            chunk_index=chunk_index,
            primary_override=primary_override,
            fallback_override=fallback_override,
            response_format=response_format,
            seen_keys=seen_keys,
            seen_lock=seen_lock,
            on_batch_persisted=on_batch_persisted,
        )
    return AiExtractionRunSummary(requirements=result.requirements, batches=[result.usage])


__all__ = [
    "AiExtractedRequirement", "AiExtractionError",
    "AiExtractionRunSummary", "BatchUsage",
    "extract_requirements_for_batch", "extract_requirements_with_ai",
]
