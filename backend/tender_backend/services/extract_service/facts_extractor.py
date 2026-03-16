"""Facts extractor — identifies key project facts from parsed sections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ExtractedFact:
    fact_key: str
    fact_value: str
    source_text: str


async def extract_facts(
    sections: list[dict[str, Any]],
    *,
    ai_gateway_url: str = "",
) -> list[ExtractedFact]:
    """Extract project facts (name, location, duration, budget, etc.) from sections.

    In production, uses AI Gateway for extraction. Currently keyword-based.
    """
    results: list[ExtractedFact] = []
    fact_patterns = {
        "project_name": ["项目名称", "工程名称"],
        "project_location": ["项目地点", "工程地点", "建设地点"],
        "construction_period": ["工期", "建设周期", "施工周期"],
        "budget": ["预算", "控制价", "招标控制价", "投资额"],
        "quality_standard": ["质量标准", "质量要求", "验收标准"],
    }

    for section in sections:
        text = section.get("text", "")
        for key, keywords in fact_patterns.items():
            for kw in keywords:
                idx = text.find(kw)
                if idx >= 0:
                    # Extract surrounding context as value
                    start = max(0, idx)
                    snippet = text[start : start + 200].strip()
                    results.append(ExtractedFact(
                        fact_key=key,
                        fact_value=snippet,
                        source_text=text[max(0, idx - 50) : idx + 200],
                    ))
                    break  # One match per key per section

    logger.info("facts_extracted", count=len(results))
    return results
