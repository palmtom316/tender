"""Ad hoc chapter task-card state machine and draft helpers.

This module intentionally stays deterministic.  It does not decide that a
normal baseline chapter is ad hoc; callers must enforce the trigger rules and
only use these helpers after a chapter has been explicitly marked ad hoc.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

VALID_STATUSES: set[str] = {
    "task_card_pending",
    "needs_input",
    "outline_ready",
    "outline_confirmed",
    "draft_ready",
    "blocked_insufficient_evidence",
}
BLOCKING_STATUSES: set[str] = {
    "task_card_pending",
    "needs_input",
    "outline_ready",
    "outline_confirmed",
    "blocked_insufficient_evidence",
}
VALID_CHAPTER_TYPES: set[str] = {"technical_special_plan", "material_attachment", "table_checklist"}

_TABLE_KEYWORDS = ("响应表", "核查表", "明细表", "汇总表", "统计表", "表", "清单", "矩阵", "台账")
_ATTACHMENT_KEYWORDS = ("证明材料", "说明材料", "承诺函", "证明", "证书", "附件", "截图", "报告")
_TECHNICAL_KEYWORDS = ("绿色施工", "临电", "临水", "停电", "应急", "方案", "措施", "布置", "专项", "组织", "保障")

_TECHNICAL_OUTLINE = (
    "编制依据",
    "工程条件与限制",
    "专项方案",
    "安全文明施工",
    "检查与验收",
    "招标要求响应表",
)
_ATTACHMENT_OUTLINE = ("材料说明", "资料清单", "附件占位符", "有效性检查")
_TABLE_OUTLINE = ("表格说明", "字段定义", "数据来源", "人工确认")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _combined_text(chapter_title: str, source_requirements: list[dict[str, Any]]) -> str:
    parts = [chapter_title]
    for requirement in source_requirements:
        parts.append(_text(requirement.get("title")))
        parts.append(_text(requirement.get("requirement_text") or requirement.get("source_text")))
    return " ".join(part for part in parts if part)


def classify_chapter_type(chapter_title: str, source_requirements: list[dict[str, Any]]) -> str:
    haystack = _combined_text(chapter_title, source_requirements)
    if any(keyword in haystack for keyword in _TABLE_KEYWORDS):
        return "table_checklist"
    if any(keyword in haystack for keyword in _ATTACHMENT_KEYWORDS):
        return "material_attachment"
    if any(keyword in haystack for keyword in _TECHNICAL_KEYWORDS):
        return "technical_special_plan"
    return "technical_special_plan"


def _questions_for_type(chapter_type: str) -> list[dict[str, Any]]:
    if chapter_type == "technical_special_plan":
        return [
            {
                "key": "site_type",
                "label": "项目现场类型",
                "input_type": "choice",
                "options": ["城区道路", "小区配网", "乡镇线路", "开关站周边", "其他"],
                "required": True,
                "answer": None,
            },
            {
                "key": "has_site_drawing",
                "label": "是否有现场图或布置图",
                "input_type": "choice",
                "options": ["uploaded", "not_available_text_only"],
                "required": True,
                "answer": None,
            },
            {
                "key": "special_constraint",
                "label": "是否有特殊施工限制",
                "input_type": "text",
                "required": False,
                "answer": None,
            },
        ]
    if chapter_type == "material_attachment":
        return [
            {
                "key": "material_source",
                "label": "资料来源",
                "input_type": "choice",
                "options": ["company_asset_library", "user_upload", "tender_required_only"],
                "required": True,
                "answer": None,
            },
            {
                "key": "attachment_required",
                "label": "是否必须上传附件",
                "input_type": "choice",
                "options": ["yes", "no"],
                "required": True,
                "answer": None,
            },
        ]
    if chapter_type == "table_checklist":
        return [
            {
                "key": "table_basis",
                "label": "表格数据来源",
                "input_type": "choice",
                "options": ["company_database", "user_input", "tender_requirement_only"],
                "required": True,
                "answer": None,
            },
            {
                "key": "manual_review_required",
                "label": "是否需要人工逐项确认",
                "input_type": "choice",
                "options": ["yes", "no"],
                "required": True,
                "answer": None,
            },
        ]
    raise ValueError(f"invalid chapter_type: {chapter_type}")


def _source_anchor(requirement: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": _text(requirement.get("id") or requirement.get("requirement_id")),
        "source_file": _text(requirement.get("source_file")) or "招标文件",
        "source_locator": _text(requirement.get("source_locator")) or "待确认",
        "text": _text(requirement.get("requirement_text") or requirement.get("source_text") or requirement.get("title")),
    }


def _must_respond(source_requirements: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for requirement in source_requirements:
        candidate = _text(requirement.get("title")) or _text(requirement.get("requirement_text") or requirement.get("source_text"))
        if not candidate:
            continue
        if candidate not in seen:
            seen.add(candidate)
            values.append(candidate)
    return values


def build_initial_task_card(
    *,
    chapter_title: str,
    source_requirements: list[dict[str, Any]],
    manual_no_source: bool = False,
) -> dict[str, Any]:
    chapter_type = classify_chapter_type(chapter_title, source_requirements)
    blocked = manual_no_source or not source_requirements
    return {
        "status": "blocked_insufficient_evidence" if blocked else "needs_input",
        "chapter_type": chapter_type,
        "source_anchors": [_source_anchor(row) for row in source_requirements],
        "must_respond": _must_respond(source_requirements),
        "missing_inputs": _questions_for_type(chapter_type),
        "outline": [],
        "draft_stale": False,
    }


def validate_task_card_status(card: dict[str, Any]) -> None:
    status = _text(card.get("status"))
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid ad hoc task card status: {status}")


def missing_required_inputs(card: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for item in card.get("missing_inputs") or []:
        if not item.get("required"):
            continue
        answer = item.get("answer")
        if answer is None or (isinstance(answer, str) and not answer.strip()):
            missing.append(str(item.get("key") or ""))
    return [key for key in missing if key]


def validate_task_card_ready_for_outline(card: dict[str, Any]) -> dict[str, Any]:
    validate_task_card_status(card)
    if card.get("status") == "blocked_insufficient_evidence":
        return {"ready": False, "missing_input_keys": missing_required_inputs(card), "blocked": True}
    missing = missing_required_inputs(card)
    return {"ready": not missing, "missing_input_keys": missing}


def validate_task_card_ready_for_draft(card: dict[str, Any]) -> None:
    validate_task_card_status(card)
    if card.get("status") == "blocked_insufficient_evidence":
        raise ValueError("insufficient evidence for ad hoc chapter generation")
    if card.get("status") != "outline_confirmed":
        raise ValueError("outline must be confirmed before draft generation")
    if missing_required_inputs(card):
        raise ValueError("required task card inputs are missing")
    if not card.get("outline"):
        raise ValueError("confirmed outline is missing")


def update_task_card_answers(card: dict[str, Any], *, answers: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(card)
    inputs = updated.get("missing_inputs") or []
    by_key = {str(item.get("key")): item for item in inputs}
    for key, value in answers.items():
        if key not in by_key:
            raise ValueError(f"unknown answer key: {key}")
        item = by_key[key]
        if item.get("input_type") == "choice" and value not in (item.get("options") or []):
            raise ValueError(f"invalid choice for {key}: {value}")
        item["answer"] = value

    if answers:
        if updated.get("status") == "draft_ready":
            updated["draft_stale"] = True
        if updated.get("status") in {"outline_ready", "outline_confirmed", "draft_ready"}:
            updated["outline"] = []
        if missing_required_inputs(updated):
            updated["status"] = "needs_input"
        elif updated.get("status") in {"task_card_pending", "needs_input", "outline_ready", "outline_confirmed", "draft_ready"}:
            updated["status"] = "task_card_pending"
    return updated


def change_task_card_type(card: dict[str, Any], *, chapter_type: str) -> dict[str, Any]:
    if chapter_type not in VALID_CHAPTER_TYPES:
        raise ValueError(f"invalid chapter_type: {chapter_type}")
    updated = deepcopy(card)
    if updated.get("chapter_type") != chapter_type:
        updated["chapter_type"] = chapter_type
        updated["missing_inputs"] = _questions_for_type(chapter_type)
        updated["outline"] = []
        updated["coverage_report"] = {}
        updated["status"] = "needs_input"
        if card.get("status") == "draft_ready":
            updated["draft_stale"] = True
    return updated


def merge_task_card_metadata(metadata: dict[str, Any] | None, card: dict[str, Any]) -> dict[str, Any]:
    merged = dict(metadata or {})
    merged["ad_hoc_task_card"] = deepcopy(card)
    return merged


def generate_task_card_outline(card: dict[str, Any]) -> list[dict[str, Any]]:
    readiness = validate_task_card_ready_for_outline(card)
    if not readiness.get("ready"):
        raise ValueError("required task card inputs are missing")
    chapter_type = card.get("chapter_type")
    headings: tuple[str, ...]
    if chapter_type == "technical_special_plan":
        headings = _TECHNICAL_OUTLINE
    elif chapter_type == "material_attachment":
        headings = _ATTACHMENT_OUTLINE
    elif chapter_type == "table_checklist":
        headings = _TABLE_OUTLINE
    else:
        raise ValueError(f"invalid chapter_type: {chapter_type}")
    must_cover = list(card.get("must_respond") or []) or ["招标要求"]
    return [
        {
            "heading": heading,
            "purpose": _outline_purpose(chapter_type=str(chapter_type), heading=heading),
            "must_cover": must_cover if heading in {"招标要求响应表", "资料清单", "字段定义", "数据来源"} else must_cover[:1],
        }
        for heading in headings
    ]


def _outline_purpose(*, chapter_type: str, heading: str) -> str:
    if chapter_type == "technical_special_plan":
        return f"围绕招标来源和已确认项目输入编写{heading}。"
    if chapter_type == "material_attachment":
        return f"组织{heading}，只引用已确认资料和附件占位符。"
    return f"形成{heading}，缺少数据时保留待确认占位。"


def _answers_map(card: dict[str, Any]) -> dict[str, Any]:
    return {str(item.get("key")): item.get("answer") for item in card.get("missing_inputs") or []}


def build_task_card_draft_markdown(card: dict[str, Any], requirements: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    validate_task_card_ready_for_draft(card)
    chapter_type = str(card.get("chapter_type"))
    outline = list(card.get("outline") or [])
    answers = _answers_map(card)
    lines: list[str] = []
    if chapter_type == "technical_special_plan":
        lines.extend(_technical_draft_lines(outline, card, answers))
    elif chapter_type == "material_attachment":
        lines.extend(_attachment_draft_lines(outline, card, answers))
    elif chapter_type == "table_checklist":
        lines.extend(_table_draft_lines(outline, card, answers))
    else:
        raise ValueError(f"invalid chapter_type: {chapter_type}")
    content = "\n".join(lines).strip() + "\n"
    coverage = _coverage_report(card, requirements, content)
    return content, coverage


def _source_anchor_lines(card: dict[str, Any]) -> list[str]:
    anchors = card.get("source_anchors") or []
    if not anchors:
        return ["- 来源：待补充招标文件来源。"]
    return [
        f"- 来源：{anchor.get('source_file') or '招标文件'} {anchor.get('source_locator') or '待确认'}；要求：{anchor.get('text') or '待确认'}"
        for anchor in anchors
    ]


def _technical_draft_lines(outline: list[dict[str, Any]], card: dict[str, Any], answers: dict[str, Any]) -> list[str]:
    lines = ["# 新增技术专项章节", ""]
    for row in outline:
        heading = _text(row.get("heading")) or "待确认"
        lines.extend([f"## {heading}", _text(row.get("purpose")) or "本节依据招标文件要求和已确认项目输入编制。"])
        if heading == "编制依据":
            lines.extend(_source_anchor_lines(card))
        elif heading == "工程条件与限制":
            lines.append(f"- 项目现场类型：{answers.get('site_type') or '待确认'}")
            lines.append(f"- 现场图或布置图：{answers.get('has_site_drawing') or '待确认'}")
            lines.append(f"- 特殊施工限制：{answers.get('special_constraint') or '待确认'}")
        elif heading == "招标要求响应表":
            lines.extend(["| 序号 | 必须响应点 | 响应章节 | 覆盖状态 |", "|---:|---|---|---|"])
            for index, item in enumerate(card.get("must_respond") or ["招标要求"], start=1):
                lines.append(f"| {index} | {item} | {heading} | 已覆盖 |")
        else:
            for item in row.get("must_cover") or card.get("must_respond") or ["招标要求"]:
                lines.append(f"- {item}：依据已确认资料编制，缺少细节时保留待确认，不作无来源承诺。")
        lines.append("")
    return lines


def _attachment_draft_lines(outline: list[dict[str, Any]], card: dict[str, Any], answers: dict[str, Any]) -> list[str]:
    lines = ["# 新增资料附件章节", ""]
    for row in outline:
        heading = _text(row.get("heading")) or "待确认"
        lines.extend([f"## {heading}"])
        if heading == "材料说明":
            lines.append(f"本章材料来源：{answers.get('material_source') or '待确认'}。")
            lines.extend(_source_anchor_lines(card))
        elif heading == "资料清单":
            lines.extend(["| 序号 | 资料名称 | 来源 | 附件位置 | 有效性 |", "|---:|---|---|---|---|"])
            for index, item in enumerate(card.get("must_respond") or ["专项资料"], start=1):
                lines.append(f"| {index} | {item} | {answers.get('material_source') or '待确认'} | {{{{ asset:ad_hoc_material_attachment:n }}}} | 待核验 |")
        elif heading == "附件占位符":
            lines.append("{{ asset:ad_hoc_material_attachment:n }}")
        else:
            lines.append("资料有效性以原件、扫描件、资料库记录和招标文件要求为准，缺失项不得编造。")
        lines.append("")
    return lines


def _table_draft_lines(outline: list[dict[str, Any]], card: dict[str, Any], answers: dict[str, Any]) -> list[str]:
    lines = ["# 新增表格清单章节", ""]
    for row in outline:
        heading = _text(row.get("heading")) or "待确认"
        lines.extend([f"## {heading}"])
        if heading == "表格说明":
            lines.append("本表依据招标文件要求和已确认资料编制。")
        elif heading == "字段定义":
            lines.extend(["| 序号 | 字段 | 内容 | 来源 | 确认状态 |", "|---:|---|---|---|---|"])
            for index, item in enumerate(card.get("must_respond") or ["招标要求字段"], start=1):
                lines.append(f"| {index} | {item} | 待确认 | {answers.get('table_basis') or '待确认'} | 待确认 |")
        elif heading == "数据来源":
            lines.append(f"- 表格数据来源：{answers.get('table_basis') or '待确认'}。")
        else:
            lines.append(f"- 是否需要人工逐项确认：{answers.get('manual_review_required') or '待确认'}。")
        lines.append("")
    return lines


def _coverage_report(card: dict[str, Any], requirements: list[dict[str, Any]], content: str) -> dict[str, Any]:
    covered_requirement_ids: list[str] = []
    missing_requirement_ids: list[str] = []
    covered_points: list[dict[str, Any]] = []
    missing_points: list[dict[str, Any]] = []
    outline_text = " ".join(
        " ".join([_text(row.get("heading")), " ".join(_text(x) for x in row.get("must_cover") or [])])
        for row in card.get("outline") or []
    )
    for requirement in requirements:
        requirement_id = _text(requirement.get("id") or requirement.get("requirement_id"))
        title = _text(requirement.get("title"))
        body = _text(requirement.get("requirement_text") or requirement.get("source_text"))
        must = title or body
        covered = bool(must and (must in outline_text or must in content))
        if covered:
            covered_requirement_ids.append(requirement_id)
            covered_points.append(
                {
                    "requirement_id": requirement_id,
                    "source_locator": _text(requirement.get("source_locator")) or "待确认",
                    "must_respond": must,
                    "covered_by_heading": _covered_heading(card, must),
                }
            )
        else:
            missing_requirement_ids.append(requirement_id)
            missing_points.append(
                {
                    "requirement_id": requirement_id,
                    "source_locator": _text(requirement.get("source_locator")) or "待确认",
                    "must_respond": must,
                    "reason": "confirmed outline 未包含该响应点",
                }
            )
    return {
        "coverage_passed": not missing_requirement_ids,
        "covered_requirement_ids": covered_requirement_ids,
        "missing_requirement_ids": missing_requirement_ids,
        "covered_points": covered_points,
        "missing_points": missing_points,
        "manual_review_required": bool(missing_requirement_ids),
        "issues": [
            {"code": "missing_ad_hoc_requirement", "severity": "P0", "requirement_id": requirement_id}
            for requirement_id in missing_requirement_ids
        ],
    }


def _covered_heading(card: dict[str, Any], must: str) -> str:
    for row in card.get("outline") or []:
        heading = _text(row.get("heading"))
        if must in heading or any(must in _text(item) or _text(item) in must for item in row.get("must_cover") or []):
            return heading
    outline = card.get("outline") or []
    return _text(outline[-1].get("heading")) if outline else "待确认"
