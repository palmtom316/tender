"""Query service — BM25 + synonym search via OpenSearch."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import structlog

logger = structlog.stdlib.get_logger(__name__)

OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")


def _query_uses_named_analyzer(body: dict) -> bool:
    try:
        must_clauses = body["bool"]["must"]
    except (KeyError, TypeError):
        return False
    return any("analyzer" in clause.get("multi_match", {}) for clause in must_clauses if isinstance(clause, dict))


def _remove_named_analyzers(body: dict) -> dict:
    must_clauses = list(body.get("bool", {}).get("must", []))
    sanitized_must: list[dict[str, Any]] = []
    for clause in must_clauses:
        current = dict(clause)
        multi_match = current.get("multi_match")
        if isinstance(multi_match, dict) and "analyzer" in multi_match:
            current["multi_match"] = {key: value for key, value in multi_match.items() if key != "analyzer"}
        sanitized_must.append(current)
    return {"bool": {"must": sanitized_must}}


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
    must = [
        {
            "multi_match": {
                "query": query,
                "fields": ["clause_title^2", "clause_text", "summary"],
                "analyzer": "cn_with_synonym",
            }
        }
    ]
    if specialty:
        must.append({"term": {"specialty": specialty}})

    body = {"bool": {"must": must}}
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
