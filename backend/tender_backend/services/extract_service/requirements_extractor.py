"""Requirements extractor — identifies and categorizes tender constraints."""

from __future__ import annotations

import os
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


SCOPE_POLICY_VERSION = "bid_writing_v1"
SCOPED_EXTRACTION_MODE_MARKER = "scoped_v1"
LEGACY_EXTRACTION_MODE_MARKER = "legacy_v0"


def extraction_scope_policy() -> str:
    value = os.environ.get("EXTRACTION_SCOPE_POLICY", "strict").strip().lower()
    return "legacy" if value == "legacy" else "strict"


def extraction_mode_marker() -> str:
    return LEGACY_EXTRACTION_MODE_MARKER if extraction_scope_policy() == "legacy" else SCOPED_EXTRACTION_MODE_MARKER

KEYWORDS_BY_CATEGORY: dict[str, list[str]] = {
    "project_info": ["项目名称", "招标编号", "采购编号", "包号", "招标人", "采购人", "采购范围", "实施地点"],
    "schedule": ["投标截止", "开标", "工期", "服务期", "交付期", "计划工期", "履约期限"],
    "qualification": ["资质", "营业执照", "资格证", "认证", "许可证", "联合体", "投标人资格"],
    "performance": ["业绩", "类似工程", "类似项目", "合同业绩", "证明材料", "竣工验收"],
    "project_team": ["项目经理", "技术负责人", "安全员", "施工员", "资料员", "人员配置", "社保"],
    "technical": [
        "技术规范",
        "技术要求",
        "质量标准",
        "质量目标",
        "优质工程",
        "验收标准",
        "施工方案",
        "施工组织",
        "施工技术",
        "安全文明施工",
        "文明施工",
        "绿色施工",
        "进度保证",
        "国网",
        "国家电网",
    ],
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

PRICING_KEYWORDS = ["报价", "投标报价", "价格", "最高限价", "控制价", "清单计价", "单价", "总价", "工程量清单"]
PRICING_ONLY_CATEGORIES = {"business"}
HUMAN_CONFIRM_CATEGORIES = {"veto", "qualification", "performance", "project_team", "special"}
HARD_CONSTRAINT_CATEGORIES = {"veto", "qualification", "performance", "project_team", "format", "special"}
MAX_REQUIREMENT_TEXT = 1200
STRUCTURED_EXTRACTION_PROMPT = """
你是招标文件解析助手。请从统一 source chunk 中抽取投标文件编写约束，
输出符合 project_requirement schema 的 JSON 数组；每条必须保留 source_file、
source_locator、页码/表格/段落定位。tender 系统不涉及报价：纯报价、最高限价、
控制价、清单计价、单价、总价等内容不要输出为投标正文约束；同一片段同时包含
非报价硬约束时，只输出资格、业绩、人员、质量、进度、安全文明施工、国网技术
要求、否决项或格式要求等非报价约束。
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


def _constraint_subtype(category: str, text: str) -> str | None:
    if category == "qualification":
        return "qualification_certificate"
    if category == "performance":
        return "performance_threshold"
    if category == "project_team":
        if any(keyword in text for keyword in ("项目经理", "技术负责人", "安全员", "施工员", "资料员", "人员", "社保")):
            if any(keyword in text for keyword in ("1名", "2名", "3名", "一名", "二名", "三名", "不少于", "至少", "人员配置")):
                return "personnel_count"
            if any(keyword in text for keyword in ("证", "资格", "注册", "职称", "社保")):
                return "personnel_certificate"
            return "personnel_count"
    if category == "schedule":
        return "schedule_target"
    if category == "scoring":
        return "technical_scoring_response"
    if category == "format":
        if any(keyword in text for keyword in ("签章", "盖章", "签字", "电子签名")):
            return "signature_seal"
        return "submission_format"
    if category == "veto":
        return "veto_rejection"
    if category == "technical":
        if any(keyword in text for keyword in ("质量目标", "质量标准", "优质工程", "合格率", "验收")):
            return "quality_target"
        if any(keyword in text for keyword in ("安全文明施工", "文明施工", "绿色施工", "安全", "风险管控")):
            return "safety_civilized"
        if any(keyword in text for keyword in ("进度保证", "进度计划", "工期保证")):
            return "schedule_target"
        if any(keyword in text for keyword in ("国网", "国家电网", "技术规范", "技术标准")):
            return "sgcc_standard_compliance"
        if any(keyword in text for keyword in ("施工方案", "施工组织", "施工技术", "施工方法")):
            return "construction_method"
    if category == "business":
        return "mandatory_attachment"
    return None


_CATEGORY_PRIORITY = {
    "veto": 0,
    "qualification": 1,
    "performance": 2,
    "project_team": 3,
    "schedule": 4,
    "technical": 5,
    "scoring": 6,
    "format": 7,
    "business": 8,
    "special": 9,
    "project_info": 10,
    "contract": 11,
}


def _scope_matched_categories(
    matched_categories: list[tuple[str, list[str]]],
    text: str,
) -> list[tuple[str, list[str]]]:
    if len(matched_categories) <= 1:
        return matched_categories
    ordered = sorted(matched_categories, key=lambda item: _CATEGORY_PRIORITY.get(item[0], 99))
    scoped: list[tuple[str, list[str]]] = []
    seen_subtypes: set[str] = set()
    for category, hits in ordered:
        subtype = _constraint_subtype(category, text)
        if category == "veto":
            scoped.append((category, hits))
            continue
        if subtype:
            if subtype in seen_subtypes:
                continue
            seen_subtypes.add(subtype)
            scoped.append((category, hits))
    return scoped or ordered[:1]


def infer_constraint_subtype(category: str, text: str) -> str | None:
    """Infer the bid-writing constraint subtype used by extraction and grouping."""
    return _constraint_subtype(category, text)


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

        matched_categories = [
            (category, hits)
            for category, hits in matched_categories
            if not (pricing_hits and category in PRICING_ONLY_CATEGORIES and hits == pricing_hits)
        ]
        matched_categories = _scope_matched_categories(matched_categories, combined)
        if not matched_categories:
            ignored_reason = "pricing_only" if pricing_hits else "background_only"
            metadata = dict(chunk.get("extraction_metadata") or {})
            metadata.update(
                {
                    "ignored_reason": ignored_reason,
                    "pricing_keywords": pricing_hits,
                    "scope_policy": SCOPE_POLICY_VERSION,
                    "extraction_mode_marker": extraction_mode_marker(),
                }
            )
            chunk["extraction_metadata"] = metadata
            continue

        for category, hits in matched_categories:
            source_locator = chunk.get("source_locator")
            source_chunk_id = str(chunk["id"]) if chunk.get("id") is not None else None
            dedupe_key = (category, source_chunk_id, source_locator)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            ignored_for_pricing = False
            confidence = _confidence(len(hits))
            is_veto = category == "veto"
            is_hard_constraint = category in HARD_CONSTRAINT_CATEGORIES
            requires_human_confirm = is_veto or category in HUMAN_CONFIRM_CATEGORIES or confidence < 0.8
            requirement_text = text[:MAX_REQUIREMENT_TEXT]
            constraint_subtype = _constraint_subtype(category, combined)
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
                        "scope_policy": SCOPE_POLICY_VERSION,
                        "extraction_mode_marker": extraction_mode_marker(),
                        "constraint_subtype": constraint_subtype,
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
