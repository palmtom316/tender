"""Deterministic longform chapter quality evidence."""

from __future__ import annotations

import math
import re
from typing import Any

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CHART_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$", re.MULTILINE)
_TABLE_SEPARATOR_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
_PAGE_BREAK_RE = re.compile(r"page-break|<w:br[^>]+type=['\"]page['\"]|---PAGE BREAK---", re.IGNORECASE)
_SECTION_HEADING_RE = re.compile(r"^(#{2,6})\s+([0-9]+(?:\.[0-9]+)*)\b.*$", re.MULTILINE)


def _weighted_text_units(content_md: str) -> int:
    chinese_chars = len(_CHINESE_RE.findall(content_md or ""))
    western_words = len(_WORD_RE.findall(content_md or ""))
    return chinese_chars + math.ceil(western_words * 1.8)


def _table_row_count(content_md: str) -> int:
    count = 0
    for match in _TABLE_ROW_RE.finditer(content_md or ""):
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if cells and all(_TABLE_SEPARATOR_RE.match(cell) for cell in cells):
            continue
        count += 1
    return count


def estimate_markdown_pages(content_md: str, *, target_pages: int | None = None) -> dict[str, Any]:
    text_units = _weighted_text_units(content_md)
    heading_count = len(_HEADING_RE.findall(content_md or ""))
    chart_count = len(_CHART_RE.findall(content_md or ""))
    table_row_count = _table_row_count(content_md)
    explicit_page_break_count = len(_PAGE_BREAK_RE.findall(content_md or ""))

    estimated_pages = round(
        max(
            1.0,
            text_units / 340
            + heading_count * 0.08
            + chart_count * 0.55
            + table_row_count * 0.06
            + explicit_page_break_count,
        ),
        2,
    )

    return {
        "target_pages": target_pages,
        "estimated_pages": estimated_pages,
        "method": "weighted_cn_chars_340_per_page_plus_structure_v1",
        "evidence": {
            "weighted_text_units": text_units,
            "heading_count": heading_count,
            "chart_count": chart_count,
            "table_row_count": table_row_count,
            "explicit_page_break_count": explicit_page_break_count,
        },
    }


def build_page_gate(
    target_pages: int | None,
    estimated_pages: float | int | None,
    actual_pages: int | None,
    actual_status: str,
) -> dict[str, Any]:
    if not target_pages:
        return {
            "page_count_passed": True,
            "page_count_status": "not_required",
            "target_pages": None,
            "minimum_required_pages": None,
            "estimated_pages": estimated_pages,
            "actual_pages": actual_pages,
            "actual_status": actual_status,
            "page_count_message": "未设置目标页数。",
        }

    minimum = math.ceil(target_pages * 0.9)
    if actual_status == "counted" and actual_pages is not None:
        passed = actual_pages >= minimum
        return {
            "page_count_passed": passed,
            "page_count_status": "passed" if passed else "failed_actual_below_minimum",
            "target_pages": target_pages,
            "minimum_required_pages": minimum,
            "estimated_pages": estimated_pages,
            "actual_pages": actual_pages,
            "actual_status": actual_status,
            "page_count_message": "实际页数达标。" if passed else f"实际 {actual_pages} 页，低于最低 {minimum} 页。",
        }

    if estimated_pages is None or float(estimated_pages) < minimum:
        return {
            "page_count_passed": False,
            "page_count_status": "failed_estimate_below_minimum",
            "target_pages": target_pages,
            "minimum_required_pages": minimum,
            "estimated_pages": estimated_pages,
            "actual_pages": actual_pages,
            "actual_status": actual_status,
            "page_count_message": f"估算页数低于最低 {minimum} 页，且实际页数未校验。",
        }

    return {
        "page_count_passed": False,
        "page_count_status": "warning_actual_unchecked",
        "target_pages": target_pages,
        "minimum_required_pages": minimum,
        "estimated_pages": estimated_pages,
        "actual_pages": actual_pages,
        "actual_status": actual_status,
        "page_count_message": "实际页数未校验，不能作为最终版导出依据。",
    }


def _present_section_codes(content_md: str) -> set[str]:
    return {match.group(2) for match in _SECTION_HEADING_RE.finditer(content_md or "")}


def _section_body(content_md: str, section_code: str) -> str:
    heading_pattern = re.compile(rf"^(#{{2,6}})\s+{re.escape(section_code)}\b.*$", re.MULTILINE)
    match = heading_pattern.search(content_md or "")
    if not match:
        return ""

    level = len(match.group(1))
    next_heading = re.search(rf"^#{{2,{level}}}\s+\S.*$", (content_md or "")[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(content_md or "")
    return (content_md or "")[match.end() : end]


def build_coverage_report(
    content_md: str,
    *,
    checklist: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    chart_keys = set(_CHART_RE.findall(content_md or ""))
    present_sections = _present_section_codes(content_md)

    for item in checklist:
        section_code = str(item.get("section_code") or "").strip()
        if not section_code:
            continue

        body = _section_body(content_md, section_code)
        if not body:
            issues.append({"code": "missing_section", "section_code": section_code, "severity": "P0"})
        else:
            min_chars = int(item.get("min_chars") or 0)
            actual_chars = _weighted_text_units(body)
            if min_chars and actual_chars < min_chars:
                issues.append(
                    {
                        "code": "section_too_short",
                        "section_code": section_code,
                        "severity": "P0",
                        "min_chars": min_chars,
                        "actual_chars": actual_chars,
                    }
                )

        for chart_key in item.get("required_charts") or []:
            if chart_key not in chart_keys:
                issues.append(
                    {"code": "missing_required_chart", "section_code": section_code, "chart_key": chart_key, "severity": "P0"}
                )
        for table_label in item.get("required_tables") or []:
            if str(table_label) not in body:
                issues.append(
                    {
                        "code": "missing_required_table",
                        "section_code": section_code,
                        "table_label": table_label,
                        "severity": "P0",
                    }
                )

    for constraint in constraints:
        metadata = constraint.get("metadata_json") or {}
        critical = constraint.get("confirmation_level") == "critical" or bool(metadata.get("has_conflict"))
        mapped_section = str(constraint.get("response_section_code") or constraint.get("mapped_section_code") or "").strip()
        if critical and mapped_section not in present_sections:
            issues.append(
                {
                    "code": "hard_constraint_uncovered",
                    "constraint_id": str(constraint.get("id") or ""),
                    "section_code": mapped_section,
                    "severity": "P0",
                }
            )

    return {
        "coverage_passed": not any(issue.get("severity") == "P0" for issue in issues),
        "issue_count": len(issues),
        "issues": issues,
        "checked_section_count": len([item for item in checklist if item.get("section_code")]),
    }


def _asset_value(asset: Any, key: str) -> Any:
    if isinstance(asset, dict):
        return asset.get(key)
    return getattr(asset, key, None)


def build_chart_closure_report(
    content_md: str,
    *,
    chart_assets: list[Any],
    inserted_chart_keys: list[str] | None = None,
    residual_placeholders: list[str] | None = None,
) -> dict[str, Any]:
    referenced = set(_CHART_RE.findall(content_md or ""))
    inserted = set(inserted_chart_keys or [])
    residual = set(residual_placeholders or [])
    by_key = {
        str(_asset_value(asset, "placeholder_key") or _asset_value(asset, "chart_type") or ""): asset
        for asset in chart_assets
        if (_asset_value(asset, "placeholder_key") or _asset_value(asset, "chart_type"))
    }
    issues: list[dict[str, Any]] = []
    approved_count = 0
    rendered_count = 0

    for key in sorted(referenced):
        asset = by_key.get(key)
        if not asset:
            issues.append({"code": "missing_chart_asset", "chart_key": key, "severity": "P0"})
        else:
            if _asset_value(asset, "status") == "approved":
                approved_count += 1
            else:
                issues.append({"code": "chart_not_approved", "chart_key": key, "severity": "P0"})
            if _asset_value(asset, "rendered_path") or _asset_value(asset, "rendered_svg"):
                rendered_count += 1
            else:
                issues.append({"code": "chart_not_rendered", "chart_key": key, "severity": "P0"})

        if inserted_chart_keys is not None and key not in inserted:
            issues.append({"code": "chart_not_inserted", "chart_key": key, "severity": "P0"})
        if key in residual:
            issues.append({"code": "chart_placeholder_residual", "chart_key": key, "severity": "P0"})

    return {
        "chart_closure_passed": not any(issue.get("severity") == "P0" for issue in issues),
        "referenced_chart_count": len(referenced),
        "asset_chart_count": len([key for key in by_key if key in referenced]),
        "approved_chart_count": approved_count,
        "rendered_chart_count": rendered_count,
        "inserted_chart_count": len(inserted),
        "residual_placeholder_count": len(residual),
        "issues": issues,
    }
