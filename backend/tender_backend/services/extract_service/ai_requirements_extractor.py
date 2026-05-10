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
    deepseek_v4_thinking_options,
    is_deepseek_v4_model,
)
from tender_backend.services.ai_gateway_client import ai_gateway_headers
from tender_backend.services.extract_service.requirements_extractor import (
    HARD_CONSTRAINT_CATEGORIES,
    HUMAN_CONFIRM_CATEGORIES,
    REQUIREMENT_CATEGORIES,
    SCOPE_POLICY_VERSION,
    infer_constraint_subtype,
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
    "只输出 JSON 对象，不要任何解释、Markdown 围栏或前后缀。"
)

_RULES_BLOCK = """\
任务：从 source_chunks 数组中抽取投标文件编写约束。

判定规则：
- 只抽取投标文件编写需要的约束。
- 商务标重点覆盖资格、业绩、公司证照、法律有效性、证明材料、签章/盖章/格式/递交要求。
- 技术标重点覆盖管理人员数量及资质、质量目标、进度目标、安全文明施工、国网工程施工技术要求、评分响应、必交技术文件。
- 否决项和文件格式要求必须保留。
- 招标人的内部说明、目录、纯页眉页脚、纯背景介绍不抽取。
- tender 系统不涉及报价。纯报价、价格、最高限价、控制价、清单计价、单价、总价、报价明细等内容不要输出 requirement。
- 同一 chunk 同时包含报价和非报价硬约束时，只输出非报价约束。
- 凡含否决、废标、无效投标、不予受理、实质性不响应、投标无效的，is_veto=true。
- 输出条款的 source_chunk_id 必须来自输入数组，严禁虚构。
- 同一 chunk 可对应 0 到多条 requirement，但同一条款不要重复输出。
"""

_SCHEMA_BLOCK = """\
输出 JSON 对象，格式固定如下：
{
  "requirements": [
    {
      "source_chunk_id": "<输入数组里的 id 字符串>",
      "category": "<必须是给定 category 之一>",
      "title": "<不超过 80 字的简短标题>",
      "requirement_text": "<不超过 500 字，保留关键数字、资质名、期限>",
      "is_veto": <bool>,
      "is_hard_constraint": <bool>,
      "ignored_for_pricing": <bool>,
      "confidence": <0~1 浮点数>
    }
  ],
  "batch_quality": {
    "has_requirements": <bool>,
    "coverage_note": "<无要求时说明原因；有缺口风险时说明风险>",
    "suspected_missing": <bool>
  }
}
"""

_PROMPT_PREFIX_TEMPLATE = """\
{rules}
严格使用以下 category 之一：{categories}。

{schema}
"""
_TABLE_RULES_BLOCK = """\
任务：从 source_chunks 中的表格与表格邻近说明中抽取投标文件编写约束。

判定规则：
- 重点识别资格表、评分表、报价参考表、人员与业绩表中的硬性约束。
- 优先输出表头、分值、条件、提交材料、否决条件、递交要求相关条目。
- 对纯数据行、空行、合计行、说明性注释不要机械重复输出。
- 若同一要求在表头和正文同时出现，只保留更完整的一条。
"""
_CRITICAL_RULES_BLOCK = """\
任务：从高风险关键片段中抽取投标文件编写约束。

判定规则：
- 重点覆盖资格、评分、否决、废标、递交、技术规范中的关键限制。
- 不做泛泛总结，只保留会影响投标有效性、得分、资格、递交完整性的条款。
- 对否决、废标、无效投标类条款优先标记 is_veto=true。
"""
_PREFILTER_SIGNAL_KEYWORDS = (
    "应",
    "须",
    "必须",
    "不得",
    "禁止",
    "提交",
    "提供",
    "递交",
    "资格",
    "资质",
    "业绩",
    "人员",
    "评分",
    "评审",
    "否决",
    "废标",
    "无效投标",
    "技术要求",
    "技术规范",
    "工期",
    "服务期",
    "合同",
    "格式",
    "盖章",
    "签章",
)
_PREFILTER_NEGATIVE_TITLE_KEYWORDS = ("目录", "封面", "前言", "说明", "概述", "声明")
_QUALITY_POLICY_MAX_TOKENS = {
    "fast_prefilter": 16_384,
    "flash_extract": 24_576,
    "table_or_critical_extract": 24_576,
    "pro_review": 32_768,
}
_REFERENCE_ONLY_PATTERNS = (
    "详见",
    "见附件",
    "参见",
    "按分类",
    "以招标公告",
    "以附件",
    "制作要求详见",
    "递交要求详见",
)


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
        "document_type": chunk.get("document_type"),
        "section_title": chunk.get("section_title"),
        "source_locator": chunk.get("source_locator"),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "sheet_name": chunk.get("sheet_name"),
        "row_start": chunk.get("row_start"),
        "row_end": chunk.get("row_end"),
        "paragraph_index": chunk.get("paragraph_index"),
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


def _chunk_text_for_prefilter(chunk: dict[str, Any]) -> str:
    parts = [
        str(chunk.get("document_type") or ""),
        str(chunk.get("section_title") or ""),
        str(chunk.get("title") or ""),
        str(chunk.get("text") or ""),
    ]
    table = chunk.get("table_json") or {}
    if table.get("rows"):
        parts.append(str(table.get("rows")))
    return " ".join(part for part in parts if part)


def _prefilter_score(chunk: dict[str, Any]) -> int:
    text = _chunk_text_for_prefilter(chunk)
    if not text.strip():
        return -10
    score = 0
    title = str(chunk.get("section_title") or chunk.get("title") or "")
    if title and any(keyword in title for keyword in _PREFILTER_NEGATIVE_TITLE_KEYWORDS):
        score -= 2
    if any(keyword in text for keyword in _PREFILTER_SIGNAL_KEYWORDS):
        score += 2
    if any(modal in text for modal in ("应", "须", "必须", "不得", "禁止")):
        score += 2
    table = chunk.get("table_json") or {}
    if table.get("rows"):
        score += 1
        if any(keyword in str(table.get("rows")) for keyword in _PREFILTER_SIGNAL_KEYWORDS):
            score += 2
    if str(chunk.get("document_type") or "") in {
        "qualification_requirement",
        "qualification_sheet",
        "technical_scoring",
        "business_scoring",
        "scoring",
        "scoring_sheet",
        "bid_submission_requirement",
    }:
        score += 3
    return score


def _select_candidate_chunks(
    batch: list[dict[str, Any]],
    *,
    quality_policy: str | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    original_count = len(batch)
    if not batch:
        return batch, {"original_chunk_count": 0, "candidate_chunk_count": 0, "prefilter_dropped_chunks": 0}
    if quality_policy in {None, "legacy", "pro_review", "table_or_critical_extract"}:
        return batch, {
            "original_chunk_count": original_count,
            "candidate_chunk_count": original_count,
            "prefilter_dropped_chunks": 0,
        }

    scored = [(chunk, _prefilter_score(chunk)) for chunk in batch]
    candidates = [chunk for chunk, score in scored if score > 0]
    if not candidates:
        fallback_keep = min(8, len(batch))
        ranked = sorted(scored, key=lambda item: item[1], reverse=True)
        candidates = [chunk for chunk, _score in ranked[:fallback_keep]]
    stats = {
        "original_chunk_count": original_count,
        "candidate_chunk_count": len(candidates),
        "prefilter_dropped_chunks": max(0, original_count - len(candidates)),
    }
    return candidates, stats


def _run_stage1_prefilter(
    batch: list[dict[str, Any]],
    *,
    quality_policy: str | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    return _select_candidate_chunks(batch, quality_policy=quality_policy)


def run_stage1_prefilter(
    batch: list[dict[str, Any]],
    *,
    quality_policy: str | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    return _run_stage1_prefilter(batch, quality_policy=quality_policy)


def _prompt_variant_for_policy(quality_policy: str | None, batch: list[dict[str, Any]]) -> str:
    policy = str(quality_policy or "").strip() or "legacy"
    if policy == "table_or_critical_extract":
        if any((chunk.get("table_json") or {}).get("rows") for chunk in batch):
            return "table"
        return "critical"
    return "general"


def _max_tokens_hint_for_policy(quality_policy: str | None) -> int | None:
    return _QUALITY_POLICY_MAX_TOKENS.get(str(quality_policy or "").strip() or "legacy")


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


def _build_prompt(batch: list[dict[str, Any]], source_file: str, *, variant: str = "general") -> str:
    rules = _RULES_BLOCK
    if variant == "table":
        rules = _TABLE_RULES_BLOCK
    elif variant == "critical":
        rules = _CRITICAL_RULES_BLOCK
    prefix = _PROMPT_PREFIX_TEMPLATE.format(
        rules=rules,
        categories=", ".join(sorted(_VALID_CATEGORIES)),
        schema=_SCHEMA_BLOCK,
    )
    payload = json.dumps(
        [_serialize_chunk_for_prompt(c) for c in batch],
        ensure_ascii=False,
    )
    short_name = source_file.split("/")[-1] if "/" in source_file else source_file
    return (
        f"{prefix}\n"
        f"抽取模式：{variant}\n"
        f"本批次文件：{short_name}\n"
        f"本批次 chunk 数：{len(batch)}\n\n"
        f"source_chunks (JSON)：\n{payload}\n"
    )


def _batch_text(batch: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for chunk in batch:
        parts.extend(
            str(value or "")
            for value in (
                chunk.get("document_type"),
                chunk.get("section_title"),
                chunk.get("title"),
                chunk.get("text"),
            )
        )
        table = chunk.get("table_json") or {}
        if table.get("rows"):
            parts.append(str(table.get("rows")))
    return " ".join(part for part in parts if part).strip()


def _reference_targets_from_text(text: str) -> list[str]:
    targets: list[str] = []
    for marker in ("附件", "招标公告", "采购文件", "评分细则", "专用资格要求", "技术规范书"):
        if marker in text and marker not in targets:
            targets.append(marker)
    return targets


def _infer_empty_batch_quality(
    *,
    source_file: str,
    batch: list[dict[str, Any]],
    llm_batch_quality: dict[str, Any] | None,
) -> dict[str, Any]:
    quality = dict(llm_batch_quality or {})
    if quality.get("has_requirements") is True:
        quality.setdefault("suspected_missing", False)
        quality.setdefault("empty_reason", None)
        quality.setdefault("reference_targets", [])
        return quality

    text = _batch_text(batch)
    filename = source_file.rsplit("/", 1)[-1]
    inferred_reason = "uncertain_missing"
    reference_targets: list[str] = []

    if any(keyword in filename for keyword in ("空白", "模板")) or (
        "空白" in text and any(keyword in text for keyword in ("模板", "待填", "示例"))
    ):
        inferred_reason = "template_blank"
    elif any(pattern in text for pattern in _REFERENCE_ONLY_PATTERNS):
        inferred_reason = "reference_only"
        reference_targets = _reference_targets_from_text(text)
    elif quality.get("suspected_missing") is False:
        inferred_reason = "true_empty"

    quality.setdefault("has_requirements", False)
    quality["empty_reason"] = str(quality.get("empty_reason") or inferred_reason)
    if quality["empty_reason"] in {"template_blank", "reference_only", "true_empty"}:
        quality["suspected_missing"] = False
    else:
        quality["suspected_missing"] = bool(quality.get("suspected_missing", True))
    quality["reference_targets"] = list(quality.get("reference_targets") or reference_targets)
    quality.setdefault("coverage_note", "")
    return quality


def _normalize_nonempty_batch_quality(batch_quality: dict[str, Any] | None) -> dict[str, Any]:
    quality = dict(batch_quality or {})
    quality["has_requirements"] = True
    quality["suspected_missing"] = bool(quality.get("suspected_missing", False))
    quality.setdefault("coverage_note", "")
    quality.setdefault("empty_reason", None)
    quality.setdefault("reference_targets", [])
    return quality


def _ai_gateway_chat_url() -> str:
    return f"{AI_GATEWAY_URL.rstrip('/')}/api/ai/chat"


def _provider_override(
    *,
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
) -> dict | None:
    if not base_url or not api_key:
        return None
    override = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model or DEEPSEEK_V4_PRO_MODEL,
    }
    if is_deepseek_v4_model(override["model"]):
        extra_body = deepseek_v4_thinking_options(
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
        )
        if extra_body:
            override["extra_body"] = extra_body
    return override


def _build_overrides(
    conn: Connection,
    *,
    model: str | None = None,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
    fallback_model: str | None = None,
    fallback_thinking_enabled: bool | None = None,
    fallback_reasoning_effort: str | None = None,
    force_legacy_max_reasoning: bool = False,
) -> tuple[dict | None, dict | None]:
    config = AgentConfigRepository().get_by_key(conn, "extract")
    if not config or not config.enabled:
        return None, None
    effective_thinking_enabled = thinking_enabled
    if effective_thinking_enabled is None and reasoning_effort is not None:
        effective_thinking_enabled = True
    effective_fallback_thinking_enabled = fallback_thinking_enabled
    if effective_fallback_thinking_enabled is None and fallback_reasoning_effort is not None:
        effective_fallback_thinking_enabled = True

    primary_model = model or config.primary_model or DEEPSEEK_V4_PRO_MODEL
    primary_effort = reasoning_effort
    if force_legacy_max_reasoning and primary_effort is None:
        primary_effort = DEEPSEEK_V4_MAX_REASONING_EFFORT
    primary = _provider_override(
        base_url=config.base_url,
        api_key=config.api_key,
        model=primary_model,
        thinking_enabled=effective_thinking_enabled,
        reasoning_effort=primary_effort,
    )

    resolved_fallback_model = fallback_model or config.fallback_model or "deepseek-v4-flash"
    fallback_effort = fallback_reasoning_effort
    if force_legacy_max_reasoning and fallback_effort is None:
        fallback_effort = DEEPSEEK_V4_MAX_REASONING_EFFORT
    fallback = _provider_override(
        base_url=config.fallback_base_url,
        api_key=config.fallback_api_key,
        model=resolved_fallback_model,
        thinking_enabled=effective_fallback_thinking_enabled,
        reasoning_effort=fallback_effort,
    )

    return primary, fallback


async def _call_ai_gateway(
    client: httpx.AsyncClient,
    *,
    prompt: str,
    primary_override: dict | None,
    fallback_override: dict | None,
    response_format: str | None = None,
    stream: bool = False,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_type": "extract_tender_requirements",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    thinking_enabled = None
    if primary_override and isinstance(primary_override.get("extra_body"), dict):
        thinking = primary_override["extra_body"].get("thinking")
        if isinstance(thinking, dict):
            thinking_enabled = thinking.get("type") == "enabled"
    if thinking_enabled is not True:
        payload["temperature"] = 0.0
    if primary_override:
        payload["primary_override"] = primary_override
    if fallback_override:
        payload["fallback_override"] = fallback_override
    if response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}
    if stream:
        payload["stream"] = True
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    resp = await client.post(
        _ai_gateway_chat_url(),
        json=payload,
        headers=ai_gateway_headers(),
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_llm_json_value(raw: str) -> Any:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = [line for line in text.split("\n") if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                result, _end = decoder.raw_decode(text[index:])
                return result
            except json.JSONDecodeError:
                continue
        logger.warning("ai_extract_json_unparseable", raw_length=len(text))
        return None


def _parse_llm_json_payload(raw: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = _parse_llm_json_value(raw)
    if isinstance(result, dict):
        requirements = result.get("requirements")
        batch_quality = result.get("batch_quality")
        if isinstance(requirements, list):
            return (
                [item for item in requirements if isinstance(item, dict)],
                batch_quality if isinstance(batch_quality, dict) else {},
            )
        return [result], batch_quality if isinstance(batch_quality, dict) else {}
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)], {}
    return [], {}


def _parse_llm_json_array(raw: str) -> list[dict[str, Any]]:
    items, _batch_quality = _parse_llm_json_payload(raw)
    return items


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
    if ignored_for_pricing:
        return None
    confidence_raw = item.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else 0.85
    except (TypeError, ValueError):
        confidence = 0.85
    confidence = max(0.0, min(1.0, confidence))

    requires_human_confirm = (
        is_veto or category in HUMAN_CONFIRM_CATEGORIES or confidence < 0.8
    )
    subtype_text = " ".join(
        part
        for part in (
            str(source_chunk.get("section_title") or ""),
            str(source_chunk.get("title") or ""),
            requirement_text,
        )
        if part
    )
    constraint_subtype = infer_constraint_subtype(category, subtype_text)

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
            "scope_policy": SCOPE_POLICY_VERSION,
            "constraint_subtype": constraint_subtype,
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
    error_message: str | None = None
    finish_reason: str | None = None
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0
    reasoning_tokens: int = 0
    batch_quality: dict[str, Any] | None = None
    prompt_cache_hit_ratio: float = 0.0
    original_chunk_count: int = 0
    candidate_chunk_count: int = 0
    prefilter_dropped_chunks: int = 0
    max_tokens_hint: int = 0
    output_tokens_to_max_ratio: float = 0.0


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
    stream: bool,
    quality_policy: str | None,
    seen_keys: set[tuple[str, str]],
    seen_lock: asyncio.Lock,
    on_batch_persisted: Callable[[list["AiExtractedRequirement"]], Awaitable[None]] | None,
) -> _BatchResult:
    candidate_batch, prefilter_stats = _run_stage1_prefilter(batch, quality_policy=quality_policy)
    if not candidate_batch:
        return _BatchResult(
            usage=BatchUsage(
                source_file=source_file,
                chunks_in_batch=0,
                extracted=0,
                dropped_invalid=0,
                input_tokens=0,
                output_tokens=0,
                used_fallback=False,
                resolved_model="",
                latency_ms=0,
                batch_quality={
                    "has_requirements": False,
                    "coverage_note": "prefilter produced no candidate chunks",
                    "suspected_missing": False,
                    "empty_reason": "true_empty",
                    "reference_targets": [],
                },
                original_chunk_count=prefilter_stats["original_chunk_count"],
                candidate_chunk_count=0,
                prefilter_dropped_chunks=prefilter_stats["prefilter_dropped_chunks"],
            ),
            requirements=[],
        )
    prompt_variant = _prompt_variant_for_policy(quality_policy, candidate_batch)
    prompt = _build_prompt(candidate_batch, source_file, variant=prompt_variant)
    max_tokens_hint = _max_tokens_hint_for_policy(quality_policy)
    try:
        response = await _call_ai_gateway(
            client, prompt=prompt, primary_override=primary_override,
            fallback_override=fallback_override, response_format=response_format,
            stream=stream,
            max_tokens=max_tokens_hint,
        )
    except Exception as exc:
        logger.exception(
            "ai_extract_batch_failed",
            source_file=source_file, batch_size=len(batch),
            error_type=type(exc).__name__,
        )
        return _BatchResult(
            usage=BatchUsage(source_file=source_file, chunks_in_batch=len(candidate_batch),
                             extracted=0, dropped_invalid=0, input_tokens=0,
                             output_tokens=0, used_fallback=False,
                             resolved_model="", latency_ms=0,
                             failed=True, error_type=type(exc).__name__,
                             error_message=str(exc),
                             original_chunk_count=prefilter_stats["original_chunk_count"],
                             candidate_chunk_count=prefilter_stats["candidate_chunk_count"],
                             prefilter_dropped_chunks=prefilter_stats["prefilter_dropped_chunks"],
                             max_tokens_hint=max_tokens_hint or 0),
            requirements=[],
        )

    content = response.get("content") or ""
    parsed_items, batch_quality = _parse_llm_json_payload(content)
    if parsed_items:
        batch_quality = _normalize_nonempty_batch_quality(batch_quality)
    else:
        batch_quality = _infer_empty_batch_quality(
            source_file=source_file,
            batch=candidate_batch,
            llm_batch_quality=batch_quality,
        )
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
        original_chunk_count=prefilter_stats["original_chunk_count"],
        candidate_chunk_count=prefilter_stats["candidate_chunk_count"],
        prefilter_dropped_chunks=prefilter_stats["prefilter_dropped_chunks"],
        extracted=len(requirements), dropped_invalid=dropped_in_batch,
        input_tokens=int(response.get("input_tokens") or 0),
        output_tokens=int(response.get("output_tokens") or 0),
        used_fallback=bool(response.get("used_fallback", False)),
        resolved_model=str(response.get("resolved_model") or ""),
        latency_ms=int(response.get("latency_ms") or 0),
        finish_reason=response.get("finish_reason"),
        prompt_cache_hit_tokens=int(response.get("prompt_cache_hit_tokens") or 0),
        prompt_cache_miss_tokens=int(response.get("prompt_cache_miss_tokens") or 0),
        reasoning_tokens=int(response.get("reasoning_tokens") or 0),
        batch_quality=batch_quality,
        prompt_cache_hit_ratio=(
            int(response.get("prompt_cache_hit_tokens") or 0)
            / max(
                1,
                int(response.get("prompt_cache_hit_tokens") or 0)
                + int(response.get("prompt_cache_miss_tokens") or 0),
            )
        ),
        max_tokens_hint=max_tokens_hint or 0,
        output_tokens_to_max_ratio=(
            int(response.get("output_tokens") or 0) / max(1, int(max_tokens_hint or 0))
            if max_tokens_hint
            else 0.0
        ),
    )
    logger.info(
        "ai_extract_batch_done",
        source_file=source_file, chunks_in_batch=len(batch),
        candidate_chunks=usage.candidate_chunk_count,
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
    stream: bool = False,
    on_batch_persisted: Callable[[list[AiExtractedRequirement]], Awaitable[None]] | None = None,
) -> AiExtractionRunSummary:
    """Run AI extraction — one batch per source_file, concurrent, with checkpoints."""
    chunk_index = {str(c["id"]): c for c in chunks if c.get("id") is not None}
    primary_override, fallback_override = _build_overrides(
        conn,
        thinking_enabled=True,
        force_legacy_max_reasoning=True,
    )

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
                    stream=stream,
                    quality_policy="legacy",
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
    conn: Connection | None = None,
    source_file: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
    fallback_model: str | None = None,
    fallback_reasoning_effort: str | None = None,
    primary_override: dict | None = None,
    fallback_override: dict | None = None,
    response_format: str | None = "json_object",
    stream: bool = False,
    quality_policy: str | None = None,
    on_batch_persisted: Callable[[list[AiExtractedRequirement]], Awaitable[None]] | None = None,
) -> AiExtractionRunSummary:
    """Run AI extraction for a preplanned batch.

    The caller owns batch status and retry behavior. This function keeps the
    model call and normalization logic shared with the legacy full-run helper.
    """
    chunk_index = {str(c["id"]): c for c in chunks if c.get("id") is not None}
    if primary_override is None and fallback_override is None:
        if conn is None:
            raise ValueError("conn is required when provider overrides are not supplied")
        primary_override, fallback_override = _build_overrides(
            conn,
            model=model,
            reasoning_effort=reasoning_effort,
            fallback_model=fallback_model,
            fallback_reasoning_effort=fallback_reasoning_effort,
        )
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
            stream=stream,
            quality_policy=quality_policy,
            seen_keys=seen_keys,
            seen_lock=seen_lock,
            on_batch_persisted=on_batch_persisted,
        )
    return AiExtractionRunSummary(requirements=result.requirements, batches=[result.usage])


def build_batch_overrides(
    conn: Connection,
    *,
    model: str | None = None,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
    fallback_model: str | None = None,
    fallback_thinking_enabled: bool | None = None,
    fallback_reasoning_effort: str | None = None,
) -> tuple[dict | None, dict | None]:
    return _build_overrides(
        conn,
        model=model,
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
        fallback_model=fallback_model,
        fallback_thinking_enabled=fallback_thinking_enabled,
        fallback_reasoning_effort=fallback_reasoning_effort,
    )


__all__ = [
    "AiExtractedRequirement", "AiExtractionError",
    "AiExtractionRunSummary", "BatchUsage",
    "build_batch_overrides",
    "extract_requirements_for_batch", "extract_requirements_with_ai",
    "run_stage1_prefilter",
]
