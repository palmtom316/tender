"""Scoring criteria extractor — structures evaluation dimensions from bid docs.

Targets scoring tables with columns like: dimension, max_score, scoring_method.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ExtractedScoringCriteria:
    dimension: str
    max_score: float
    scoring_method: str | None
    source_page: int | None = None


async def extract_scoring_criteria(
    tables: list[dict[str, Any]],
    *,
    ai_gateway_url: str = "",
) -> list[ExtractedScoringCriteria]:
    """Extract scoring criteria from parsed tables.

    Looks for tables with scoring-related headers and extracts
    evaluation dimensions, maximum scores, and scoring methods.
    In production, enhanced by AI Gateway for complex table parsing.
    """
    results: list[ExtractedScoringCriteria] = []
    scoring_headers = ["评分项", "评分内容", "评审因素", "评分标准", "分值", "得分"]

    for table in tables:
        raw = table.get("data", table.get("raw_json", {}))
        if isinstance(raw, str):
            import json
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

        # Detect if this is a scoring table by checking headers
        headers = []
        rows: list[list[str]] = []
        if isinstance(raw, dict):
            headers = raw.get("headers", [])
            rows = raw.get("rows", [])
        elif isinstance(raw, list) and len(raw) > 0:
            headers = raw[0] if isinstance(raw[0], list) else []
            rows = raw[1:] if len(raw) > 1 else []

        header_text = " ".join(str(h) for h in headers)
        if not any(kw in header_text for kw in scoring_headers):
            continue

        # Try to find dimension and score columns
        dim_col = _find_column(headers, ["评分项", "评分内容", "评审因素", "评分标准"])
        score_col = _find_column(headers, ["分值", "最高分", "满分"])
        method_col = _find_column(headers, ["评分方法", "评分办法", "评审标准"])

        for row in rows:
            if dim_col is None or dim_col >= len(row):
                continue
            dimension = str(row[dim_col]).strip()
            if not dimension:
                continue
            max_score = 0.0
            if score_col is not None and score_col < len(row):
                try:
                    max_score = float(str(row[score_col]).strip())
                except ValueError:
                    pass
            method = None
            if method_col is not None and method_col < len(row):
                method = str(row[method_col]).strip() or None

            results.append(ExtractedScoringCriteria(
                dimension=dimension,
                max_score=max_score,
                scoring_method=method,
                source_page=table.get("page"),
            ))

    logger.info("scoring_criteria_extracted", count=len(results))
    return results


def _find_column(headers: list, keywords: list[str]) -> int | None:
    for i, h in enumerate(headers):
        for kw in keywords:
            if kw in str(h):
                return i
    return None
