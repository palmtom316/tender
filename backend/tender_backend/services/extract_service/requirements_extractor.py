"""Requirements extractor — identifies and categorizes bid requirements.

Categories: veto (否决项), qualification (资质), personnel (人员),
performance (业绩), technical (技术), scoring (评分标准), format (格式要求)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)

REQUIREMENT_CATEGORIES = [
    "veto",           # 否决项
    "qualification",  # 资质
    "personnel",      # 人员
    "performance",    # 业绩
    "technical",      # 技术
    "scoring",        # 评分标准 (B-02)
    "format",         # 格式要求 (B-06)
]


@dataclass
class ExtractedRequirement:
    category: str
    title: str
    source_text: str
    source_page: int | None = None
    confidence: float = 0.0


async def extract_requirements(
    sections: list[dict[str, Any]],
    *,
    ai_gateway_url: str = "",
) -> list[ExtractedRequirement]:
    """Extract requirements from parsed document sections using AI.

    In production, this calls the AI Gateway to classify each section.
    For now, implements keyword-based heuristic extraction.
    """
    results: list[ExtractedRequirement] = []

    veto_keywords = ["否决", "废标", "无效标", "不予受理", "不合格"]
    qual_keywords = ["资质", "营业执照", "资格证", "ISO", "认证"]
    personnel_keywords = ["项目经理", "技术负责人", "安全员", "施工员", "人员"]
    perf_keywords = ["业绩", "类似工程", "合同", "竣工验收"]
    format_keywords = ["字体", "字号", "行距", "页边距", "装订", "封面"]

    for section in sections:
        text = section.get("text", "")
        title = section.get("title", "")
        page = section.get("page_start")
        combined = f"{title} {text}"

        if any(kw in combined for kw in veto_keywords):
            results.append(ExtractedRequirement(
                category="veto", title=title, source_text=text[:500], source_page=page,
            ))
        if any(kw in combined for kw in qual_keywords):
            results.append(ExtractedRequirement(
                category="qualification", title=title, source_text=text[:500], source_page=page,
            ))
        if any(kw in combined for kw in personnel_keywords):
            results.append(ExtractedRequirement(
                category="personnel", title=title, source_text=text[:500], source_page=page,
            ))
        if any(kw in combined for kw in perf_keywords):
            results.append(ExtractedRequirement(
                category="performance", title=title, source_text=text[:500], source_page=page,
            ))
        if any(kw in combined for kw in format_keywords):
            results.append(ExtractedRequirement(
                category="format", title=title, source_text=text[:500], source_page=page,
            ))

    logger.info("requirements_extracted", count=len(results))
    return results
