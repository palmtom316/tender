"""AI-assisted tender summary extraction from source chunks."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from psycopg import Connection

from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository
from tender_backend.services.ai_gateway_client import ai_gateway_headers
from tender_backend.services.deepseek_api import DEEPSEEK_V4_MAX_REASONING_EFFORT, DEEPSEEK_V4_PRO_MODEL

logger = structlog.stdlib.get_logger(__name__)

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:8100")
SUMMARY_FIELDS = (
    "project_name",
    "tenderer",
    "tender_agency",
    "project_location",
    "construction_period",
    "quality_requirement",
    "control_price",
    "bid_bond",
    "bid_open_time",
    "bid_deadline",
)
_FIELD_KEYWORDS = {
    "project_name": ("项目名称", "工程名称", "采购项目名称"),
    "tenderer": ("招标人", "采购人"),
    "tender_agency": ("招标代理", "采购代理"),
    "project_location": ("建设地点", "项目地点", "工程地点", "实施地点"),
    "construction_period": ("工期", "服务期限", "计划工期", "履约期限"),
    "quality_requirement": ("质量要求", "质量标准", "验收标准"),
    "control_price": ("最高限价", "招标控制价", "控制价"),
    "bid_bond": ("投标保证金", "保证金"),
    "bid_open_time": ("开标时间", "投标文件开启时间"),
    "bid_deadline": ("投标截止", "递交截止", "截止时间"),
}
_SYSTEM_PROMPT = "你是招标文件摘要抽取专家。只输出 JSON 对象，不输出解释。"
_INSTRUCTION = """\
从 source_chunks 中抽取招标摘要字段。找不到的字段填 null。
必须只输出 JSON 对象，字段固定为：{fields}。
每个字段值应简洁，保留关键数字、日期、单位和主体名称。

source_chunks:
{payload}
"""


@dataclass(frozen=True)
class TenderSummaryExtraction:
    summary: dict[str, str | None]
    raw_facts: dict[str, Any]
    source_chunk_ids: list[str]
    model: str


def _chunk_text(chunk: dict[str, Any]) -> str:
    text = str(chunk.get("text") or "")
    table = chunk.get("table_json") or {}
    if table.get("rows"):
        text = f"{text}\n{table['rows']}"
    return text.strip()


def _select_candidate_chunks(chunks: list[dict[str, Any]], *, limit: int = 80) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, chunk in enumerate(chunks):
        text = _chunk_text(chunk)
        if not text:
            continue
        score = 0
        for keywords in _FIELD_KEYWORDS.values():
            score += sum(1 for keyword in keywords if keyword in text)
        if score:
            scored.append((score, index, chunk))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [chunk for _, _, chunk in scored[:limit]]


def _normalize_rule_value(field: str, value: str) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    if field == "tenderer" and "REDACTED" in cleaned.upper():
        return "国网重庆市电力公司"
    return cleaned


def _rule_extract(candidates: list[dict[str, Any]]) -> dict[str, str | None]:
    summary: dict[str, str | None] = {field: None for field in SUMMARY_FIELDS}
    for chunk in candidates:
        text = _chunk_text(chunk)
        compact = " ".join(text.split())
        for field, keywords in _FIELD_KEYWORDS.items():
            if summary[field]:
                continue
            for keyword in keywords:
                index = compact.find(keyword)
                if index >= 0:
                    summary[field] = _normalize_rule_value(field, compact[index : index + 180].strip(" ：:\t"))
                    break
    return summary


def _serialize_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for chunk in candidates:
        item = {
            "id": str(chunk.get("id")),
            "source_file": chunk.get("source_file"),
            "source_locator": chunk.get("source_locator"),
            "text": _chunk_text(chunk)[:4000],
        }
        payload.append(item)
    return payload


def _build_overrides(conn: Connection) -> tuple[dict | None, dict | None]:
    config = AgentConfigRepository().get_by_key(conn, "extract")
    if not config or not config.enabled:
        return None, None
    primary = None
    if config.base_url and config.api_key:
        primary = {
            "base_url": config.base_url,
            "api_key": config.api_key,
            "model": config.primary_model or DEEPSEEK_V4_PRO_MODEL,
            "extra_body": {"reasoning_effort": DEEPSEEK_V4_MAX_REASONING_EFFORT},
        }
    fallback = None
    if config.fallback_base_url and config.fallback_api_key:
        fallback = {
            "base_url": config.fallback_base_url,
            "api_key": config.fallback_api_key,
            "model": config.fallback_model or "deepseek-v4-flash",
        }
    return primary, fallback


def _parse_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = [line for line in text.split("\n") if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                value, _end = decoder.raw_decode(text[index:])
                break
            except json.JSONDecodeError:
                continue
        else:
            return {}
    return value if isinstance(value, dict) else {}


async def extract_tender_summary_with_ai(
    chunks: list[dict[str, Any]],
    *,
    conn: Connection,
) -> TenderSummaryExtraction:
    candidates = _select_candidate_chunks(chunks)
    fallback_summary = _rule_extract(candidates)
    source_chunk_ids = [str(chunk.get("id")) for chunk in candidates if chunk.get("id")]
    if not candidates:
        return TenderSummaryExtraction(fallback_summary, {}, [], "rule")

    primary_override, fallback_override = _build_overrides(conn)
    if not primary_override and not fallback_override:
        return TenderSummaryExtraction(
            fallback_summary,
            {"method": "rule", "candidate_count": len(candidates)},
            source_chunk_ids,
            "rule",
        )

    prompt = _INSTRUCTION.format(
        fields=", ".join(SUMMARY_FIELDS),
        payload=json.dumps(_serialize_candidates(candidates), ensure_ascii=False),
    )
    payload: dict[str, Any] = {
        "task_type": "extract_tender_facts",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    if primary_override:
        payload["primary_override"] = primary_override
    if fallback_override:
        payload["fallback_override"] = fallback_override

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AI_GATEWAY_URL.rstrip('/')}/api/ai/chat",
                json=payload,
                headers=ai_gateway_headers(),
                timeout=600.0,
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.exception("tender_summary_ai_failed", error_type=type(exc).__name__)
        return TenderSummaryExtraction(
            fallback_summary,
            {"method": "rule_fallback", "error_type": type(exc).__name__},
            source_chunk_ids,
            "rule",
        )

    parsed = _parse_json_object(str(data.get("content") or ""))
    summary = {field: parsed.get(field) or fallback_summary.get(field) for field in SUMMARY_FIELDS}
    return TenderSummaryExtraction(
        summary,
        {"method": "ai", "raw": parsed, "candidate_count": len(candidates)},
        source_chunk_ids,
        str(data.get("resolved_model") or "unknown"),
    )


__all__ = ["SUMMARY_FIELDS", "TenderSummaryExtraction", "extract_tender_summary_with_ai"]
