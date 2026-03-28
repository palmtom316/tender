"""Query service — BM25 + synonym search via OpenSearch."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
import structlog

logger = structlog.stdlib.get_logger(__name__)

OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
_QUERY_SPLIT_SUFFIXES = (
    "安装",
    "施工",
    "验收",
    "调试",
    "设计",
    "检查",
    "试验",
    "维护",
    "保养",
    "连接",
)


def _query_uses_named_analyzer(body: dict) -> bool:
    def _contains_analyzer(value: Any) -> bool:
        if isinstance(value, dict):
            multi_match = value.get("multi_match")
            if isinstance(multi_match, dict) and "analyzer" in multi_match:
                return True
            return any(_contains_analyzer(item) for item in value.values())
        if isinstance(value, list):
            return any(_contains_analyzer(item) for item in value)
        return False

    return _contains_analyzer(body)


def _remove_named_analyzers(body: dict) -> dict:
    def _strip(value: Any) -> Any:
        if isinstance(value, dict):
            multi_match = value.get("multi_match")
            if isinstance(multi_match, dict) and "analyzer" in multi_match:
                next_value = dict(value)
                next_value["multi_match"] = {
                    key: item for key, item in multi_match.items() if key != "analyzer"
                }
                return {key: _strip(item) for key, item in next_value.items()}
            return {key: _strip(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_strip(item) for item in value]
        return value

    return _strip(body)


def _split_query_terms(query: str) -> list[str]:
    trimmed = query.strip()
    if not trimmed:
        return []

    terms: list[str] = [trimmed]
    seen = {trimmed}

    for token in re.split(r"\s+", trimmed):
        normalized = token.strip()
        if len(normalized) >= 2 and normalized not in seen:
            terms.append(normalized)
            seen.add(normalized)

    compact = re.sub(r"\s+", "", trimmed)
    if compact and compact not in seen:
        terms.append(compact)
        seen.add(compact)

    for suffix in _QUERY_SPLIT_SUFFIXES:
        if compact.endswith(suffix) and len(compact) > len(suffix):
            prefix = compact[: -len(suffix)].strip()
            for part in (prefix, suffix):
                if len(part) >= 2 and part not in seen:
                    terms.append(part)
                    seen.add(part)

    return terms


def _build_clause_search_query(query: str, *, specialty: str | None = None) -> dict:
    fields = ["standard_name^3", "clause_title^2", "clause_text", "summary"]
    should = [
        {
            "multi_match": {
                "query": term,
                "fields": fields,
                "analyzer": "cn_with_synonym",
            }
        }
        for term in _split_query_terms(query)
    ]

    must: list[dict[str, Any]] = [{"bool": {"should": should, "minimum_should_match": 1}}]
    if specialty:
        must.append({"term": {"specialty": specialty}})
    return {"bool": {"must": must}}


def _is_missing_named_analyzer_error(exc: httpx.HTTPStatusError) -> bool:
    response = exc.response
    if response.status_code != 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    message = json.dumps(payload, ensure_ascii=False)
    return "analyzer" in message and "not found" in message


async def _search(index: str, body: dict, top_k: int = 5) -> list[dict]:
    """Execute an OpenSearch query and return hits."""
    async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{OPENSEARCH_URL}/{index}/_search",
                json={"query": body, "size": top_k},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            if not _query_uses_named_analyzer(body) or not _is_missing_named_analyzer_error(exc):
                raise
            fallback_body = _remove_named_analyzers(body)
            logger.warning("search_fallback_without_named_analyzer", index=index)
            fallback_resp = await client.post(
                f"{OPENSEARCH_URL}/{index}/_search",
                json={"query": fallback_body, "size": top_k},
            )
            fallback_resp.raise_for_status()
            data = fallback_resp.json()
    hits = data.get("hits", {}).get("hits", [])
    return [
        {"_id": h["_id"], "_score": h["_score"], **h.get("_source", {})}
        for h in hits
    ]


async def search_clauses(
    query: str,
    *,
    specialty: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Search standard clauses using BM25 with cn_with_synonym analyzer."""
    body = _build_clause_search_query(query, specialty=specialty)
    results = await _search("clause_index", body, top_k)
    logger.info("search_clauses", query=query, hits=len(results))
    return results


async def search_standard_clauses(
    query: str,
    *,
    specialty: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Semantic wrapper for standards workbench clause search."""
    return await search_clauses(query, specialty=specialty, top_k=top_k)


async def search_sections(
    query: str,
    *,
    project_id: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Search document sections using BM25 with cn_with_synonym analyzer."""
    must = [
        {
            "multi_match": {
                "query": query,
                "fields": ["title^2", "text"],
                "analyzer": "cn_with_synonym",
            }
        }
    ]
    if project_id:
        must.append({"term": {"project_id": project_id}})

    body = {"bool": {"must": must}}
    results = await _search("section_index", body, top_k)
    logger.info("search_sections", query=query, hits=len(results))
    return results


async def search_requirements(
    query: str,
    *,
    project_id: str | None = None,
    category: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Search project requirements."""
    must = [
        {
            "multi_match": {
                "query": query,
                "fields": ["title^2", "source_text"],
                "analyzer": "cn_with_synonym",
            }
        }
    ]
    if project_id:
        must.append({"term": {"project_id": project_id}})
    if category:
        must.append({"term": {"category": category}})

    body = {"bool": {"must": must}}
    results = await _search("requirement_index", body, top_k)
    logger.info("search_requirements", query=query, hits=len(results))
    return results
