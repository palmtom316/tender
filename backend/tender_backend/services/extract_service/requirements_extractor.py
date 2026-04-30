"""Requirements extractor — identifies and categorizes tender constraints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)

REQUIREMENT_CATEGORIES = [
    "project_info",
    "schedule",
    "qualification",
    "performance",
    "project_team",
    "technical",
    "business",
    "scoring",
    "veto",
    "format",
    "contract",
    "special",
]


@dataclass
class ExtractedRequirement:
    category: str
    title: str
    source_text: str = ""
    requirement_text: str = ""
    source_file: str | None = None
    source_locator: str | None = None
    source_page: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    paragraph_index: int | None = None
    confidence: float = 0.0
    is_veto: bool = False
    requires_human_confirm: bool = False
    ignored_for_pricing: bool = False
    is_hard_constraint: bool = False
    source_chunk_id: str | None = None
    source_metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


KEYWORDS_BY_CATEGORY: dict[str, list[str]] = {
    "project_info": ["项目名称", "招标编号", "采购编号", "包号", "招标人", "采购人", "采购范围", "实施地点"],
    "schedule": ["投标截止", "开标", "工期", "服务期", "交付期", "计划工期", "履约期限"],
    "qualification": ["资质", "营业执照", "资格证", "认证", "许可证", "联合体", "投标人资格"],
    "performance": ["业绩", "类似工程", "类似项目", "合同业绩", "证明材料", "竣工验收"],
    "project_team": ["项目经理", "技术负责人", "安全员", "施工员", "资料员", "人员配置", "社保"],
    "technical": ["技术规范", "技术要求", "质量标准", "验收标准", "施工方案", "服务范围"],
    "business": ["保证金", "履约保证", "响应文件", "商务要求", "承诺函", "商务文件", "商务投标文件"],
    "scoring": ["评分", "评审", "分值", "评分标准", "评分办法", "评标办法"],
    "veto": ["否决", "废标", "无效投标", "无效标", "不予受理", "实质性不响应", "投标无效"],
    "format": [
        "格式",
        "签章",
        "盖章",
        "页码",
        "目录",
        "装订",
        "文件命名",
        "上传方式",
        "字体",
        "字号",
        "行距",
        "投标文件组成",
        "投标文件目录",
        "资格审查文件",
        "商务文件目录",
        "技术文件目录",
        "技术投标文件",
    ],
    "contract": ["合同", "违约", "质保", "质量保证", "安全责任", "验收", "进度"],
    "special": ["分包", "现场踏勘", "澄清", "答疑", "保密", "属地化", "材料品牌", "特殊工艺", "平台上传"],
}

PRICING_KEYWORDS = ["报价", "投标报价", "价格", "最高限价", "控制价", "清单计价", "单价", "总价"]
PRICING_ONLY_CATEGORIES = {"business"}
HUMAN_CONFIRM_CATEGORIES = {"veto", "qualification", "performance", "project_team", "special"}
HARD_CONSTRAINT_CATEGORIES = {"veto", "qualification", "performance", "project_team", "format", "special"}
MAX_REQUIREMENT_TEXT = 1200
STRUCTURED_EXTRACTION_PROMPT = """
你是招标文件解析助手。请从统一 source chunk 中抽取投标文件编写约束，
输出符合 project_requirement schema 的 JSON 数组；每条必须保留 source_file、
source_locator、页码/表格/段落定位，报价相关内容只标记 ignored_for_pricing=true，
不得进入投标正文约束。
""".strip()


def _compact_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _source_title(chunk: dict[str, Any], category: str) -> str:
    explicit = chunk.get("section_title") or chunk.get("title")
    if explicit:
        return str(explicit)[:120]
    source_file = chunk.get("source_file") or "来源文件"
    return f"{source_file} - {category}"


def _confidence(hit_count: int, *, pricing_only: bool = False) -> float:
    if pricing_only:
        return 0.72
    return min(0.95, 0.72 + hit_count * 0.07)


def extract_requirements_from_source_chunks(chunks: list[dict[str, Any]]) -> list[ExtractedRequirement]:
    """Rule-based pre-extraction from normalized source chunks.

    This intentionally favors recall over precision. Low-confidence and critical
    categories are marked for human confirmation before final export.
    """
    results: list[ExtractedRequirement] = []
    seen: set[tuple[str, str | None, str | None]] = set()

    for chunk in chunks:
        text = _compact_text(chunk.get("text") or "")
        if not text:
            continue
        combined = _compact_text(f"{chunk.get('section_title') or chunk.get('title') or ''} {text}")
        if not combined:
            continue

        pricing_hits = [kw for kw in PRICING_KEYWORDS if kw in combined]
        matched_categories: list[tuple[str, list[str]]] = []
        for category, keywords in KEYWORDS_BY_CATEGORY.items():
            hits = [kw for kw in keywords if kw in combined]
            if hits:
                matched_categories.append((category, hits))

        if pricing_hits and not matched_categories:
            matched_categories.append(("business", pricing_hits))

        for category, hits in matched_categories:
            source_locator = chunk.get("source_locator")
            source_chunk_id = str(chunk["id"]) if chunk.get("id") is not None else None
            dedupe_key = (category, source_chunk_id, source_locator)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            ignored_for_pricing = bool(pricing_hits) and category in PRICING_ONLY_CATEGORIES and hits == pricing_hits
            confidence = _confidence(len(hits), pricing_only=ignored_for_pricing and len(matched_categories) == 1)
            is_veto = category == "veto"
            is_hard_constraint = category in HARD_CONSTRAINT_CATEGORIES
            requires_human_confirm = is_veto or category in HUMAN_CONFIRM_CATEGORIES or confidence < 0.8
            requirement_text = text[:MAX_REQUIREMENT_TEXT]
            results.append(
                ExtractedRequirement(
                    category=category,
                    title=_source_title(chunk, category),
                    requirement_text=requirement_text,
                    source_text=requirement_text,
                    source_file=chunk.get("source_file"),
                    source_locator=source_locator,
                    source_page=chunk.get("page_start"),
                    page_start=chunk.get("page_start"),
                    page_end=chunk.get("page_end"),
                    sheet_name=chunk.get("sheet_name"),
                    row_start=chunk.get("row_start"),
                    row_end=chunk.get("row_end"),
                    paragraph_index=chunk.get("paragraph_index"),
                    confidence=confidence,
                    is_veto=is_veto,
                    requires_human_confirm=requires_human_confirm,
                    ignored_for_pricing=ignored_for_pricing,
                    is_hard_constraint=is_hard_constraint,
                    source_chunk_id=source_chunk_id,
                    source_metadata={
                        "matched_keywords": hits,
                        "pricing_keywords": pricing_hits,
                        "chunk_type": chunk.get("chunk_type"),
                    },
                )
            )

    logger.info("source_chunk_requirements_extracted", count=len(results), chunk_count=len(chunks))
    return results


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

    normalized_chunks = []
    for index, section in enumerate(sections):
        normalized_chunks.append(
            {
                "id": section.get("id"),
                "chunk_type": "section",
                "source_file": section.get("source_file"),
                "source_locator": section.get("source_locator") or f"section:{index + 1}",
                "section_title": section.get("title"),
                "title": section.get("title"),
                "text": section.get("text", ""),
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end") or section.get("page_start"),
            }
        )
    results = extract_requirements_from_source_chunks(normalized_chunks)
    logger.info("requirements_extracted", count=len(results))
    return results
