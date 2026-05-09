"""Plan bid document outlines from confirmed tender requirements."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from psycopg import Connection

from tender_backend.db.repositories.bid_outline_repo import BidOutlineRepository
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.services.bid_outline_templates import (
    PRIORITY_POLICY,
    SGCC_DISTRIBUTION_BUSINESS_TEMPLATE_KEY,
    SGCC_DISTRIBUTION_TECHNICAL_TEMPLATE_KEY,
    base_bid_chapters,
)


CATEGORY_CHAPTER = {
    "qualification": ("qualification", "1.1"),
    "performance": ("qualification", "1.2"),
    "project_team": ("qualification", "1.3"),
    "personnel": ("technical", "6"),
    "project_info": ("business", "5"),
    "business": ("business", "24.6"),
    "pricing": ("business", "23"),
    "contract": ("business", "24.6"),
    "schedule": ("technical", "3"),
    "format": ("business", "24.6"),
    "technical": ("technical", "8.1"),
    "scoring": ("technical", "12"),
    "veto": ("technical", "1"),
    "special": ("technical", "15"),
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _requirement_summary(requirement: dict[str, Any]) -> str:
    title = _clean_text(requirement.get("title")) or "未命名约束"
    source = _clean_text(requirement.get("source_locator"))
    if source:
        return f"[{requirement.get('category')}] {title}（{source}）"
    return f"[{requirement.get('category')}] {title}"


def _mapping_reason(requirement: dict[str, Any], volume_type: str, chapter_code: str) -> str:
    category = requirement.get("category")
    if volume_type == "technical" and chapter_code == "1" and (requirement.get("is_veto") or requirement.get("is_hard_constraint")):
        return "否决项或硬约束必须设置专门响应章节"
    if category == "scoring":
        return "评分项必须逐项响应"
    if category == "special":
        return "特殊要求必须独立响应"
    return "按招标文件解析出的约束类别映射"


def _priority_level(requirement: dict[str, Any], volume_type: str, chapter_code: str) -> str:
    if (volume_type == "technical" and chapter_code == "1") or requirement.get("is_veto") or requirement.get("is_hard_constraint"):
        return "hard"
    if requirement.get("category") == "scoring":
        return "scoring"
    if requirement.get("category") == "special":
        return "special"
    return "normal"


def _chapter_keys_for_requirement(requirement: dict[str, Any]) -> list[tuple[str, str]]:
    category = requirement.get("category")
    keys = [CATEGORY_CHAPTER.get(category, ("technical", "8.1"))]
    if requirement.get("is_veto") or requirement.get("is_hard_constraint"):
        keys.append(("technical", "1"))
    if category == "scoring":
        keys.append(("technical", "12"))
    if category == "special":
        keys.append(("technical", "15"))
    return list(dict.fromkeys(keys))


def _build_outline_md(chapter: dict[str, Any], requirements: list[dict[str, Any]]) -> str:
    heading = f"# {chapter['chapter_code']} {chapter['chapter_title']}"
    lines = [
        heading,
        "",
        "- 以招标文件 AI 解析结果为最高优先级，模板内容仅作为补充。",
        f"- 本章节需响应 {len(requirements)} 项解析约束。",
    ]
    if requirements:
        lines.extend(["- 输入约束："])
        for requirement in requirements:
            lines.append(f"  - {_requirement_summary(requirement)}")
    else:
        lines.append("- 暂无明确解析约束，保留章节占位并等待人工补充。")
    return "\n".join(lines)


def plan_bid_outline_from_requirements(
    *,
    project_id: UUID | str,
    requirements: list[dict[str, Any]],
    outline_name: str = "投标文件目录草案",
) -> dict[str, Any]:
    """Create a deterministic bid outline and chapter-requirement mappings."""

    active_requirements = [
        row
        for row in requirements
        if not row.get("ignored_for_pricing") and row.get("review_status") != "rejected"
    ]
    requirements_by_chapter: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for requirement in active_requirements:
        for chapter_key in _chapter_keys_for_requirement(requirement):
            requirements_by_chapter[chapter_key].append(requirement)

    chapters: list[dict[str, Any]] = []
    for index, chapter in enumerate(base_bid_chapters(), start=1):
        chapter_key = (chapter["volume_type"], chapter["chapter_code"])
        chapter_requirements = requirements_by_chapter.get(chapter_key, [])
        mappings = [
            {
                "requirement_id": requirement["id"],
                "mapping_reason": _mapping_reason(requirement, chapter["volume_type"], chapter["chapter_code"]),
                "priority_level": _priority_level(requirement, chapter["volume_type"], chapter["chapter_code"]),
            }
            for requirement in chapter_requirements
        ]
        chapters.append(
            {
                **chapter,
                "project_id": project_id,
                "sort_order": index,
                "outline_md": _build_outline_md(chapter, chapter_requirements),
                "requirement_ids": [mapping["requirement_id"] for mapping in mappings],
                "requirement_mappings": mappings,
                "metadata_json": {
                    **dict(chapter.get("metadata_json") or {}),
                    "requirement_count": len(chapter_requirements),
                    "priority_policy": PRIORITY_POLICY,
                },
                "parent_code": chapter.get("parent_code"),
            }
        )

    hard_requirement_ids = {
        str(row["id"])
        for row in active_requirements
        if row.get("is_veto") or row.get("is_hard_constraint") or row.get("category") in {"veto", "scoring", "special"}
    }
    mapped_requirement_ids = {
        str(mapping["requirement_id"])
        for chapter in chapters
        for mapping in chapter["requirement_mappings"]
    }

    return {
        "project_id": project_id,
        "outline_name": outline_name,
        "status": "draft",
        "metadata_json": {
            "priority_policy": PRIORITY_POLICY,
            "source_requirement_count": len(active_requirements),
            "hard_requirement_count": len(hard_requirement_ids),
            "unmapped_hard_requirement_ids": sorted(hard_requirement_ids - mapped_requirement_ids),
            "volume_types": ["qualification", "business", "technical"],
            "business_outline_template_key": SGCC_DISTRIBUTION_BUSINESS_TEMPLATE_KEY,
            "technical_outline_template_key": SGCC_DISTRIBUTION_TECHNICAL_TEMPLATE_KEY,
        },
        "chapters": chapters,
    }


def build_bid_outline(conn: Connection, *, project_id: UUID) -> dict[str, Any]:
    """Load project requirements, plan the outline, and persist it."""

    requirement_repo = RequirementRepository()
    outline_repo = BidOutlineRepository()
    requirements = requirement_repo.list_by_project(conn, project_id=project_id)
    outline = plan_bid_outline_from_requirements(project_id=project_id, requirements=requirements)
    return outline_repo.replace_for_project(conn, project_id=project_id, outline=outline)
