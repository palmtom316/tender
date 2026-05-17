"""Deterministic longform chapter quality evidence."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
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

    minimum = math.ceil(target_pages * 0.7)
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
        "page_count_passed": True,
        "page_count_status": "passed_by_estimate",
        "target_pages": target_pages,
        "minimum_required_pages": minimum,
        "estimated_pages": estimated_pages,
        "actual_pages": actual_pages,
        "actual_status": actual_status,
        "page_count_message": f"估算页数 {estimated_pages} 已超过最低 {minimum} 页，实际页数将在导出后回填校验。",
    }


def _present_section_codes(content_md: str) -> set[str]:
    return {match.group(2) for match in _SECTION_HEADING_RE.finditer(content_md or "")}


def _section_body(content_md: str, section_code: str) -> str:
    heading_pattern = re.compile(rf"^(#{{2,6}})\s+{re.escape(section_code)}(?=\s|$).*$", re.MULTILINE)
    matches = list(heading_pattern.finditer(content_md or ""))
    if not matches:
        return ""

    # 选择同节多次出现时“信息量最高”的正文，避免前置空壳标题把本节误判为 0 字。
    best_body = ""
    best_units = -1
    source = content_md or ""
    for match in matches:
        level = len(match.group(1))
        next_heading = re.search(rf"^#{{2,{level}}}\s+\S.*$", source[match.end() :], re.MULTILINE)
        end = match.end() + next_heading.start() if next_heading else len(source)
        body = source[match.end() : end]
        units = _weighted_text_units(body)
        if units > best_units:
            best_units = units
            best_body = body
    return best_body


def build_coverage_report(
    content_md: str,
    *,
    checklist: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    equipment_data: dict[str, list[Any]] | None = None,
    personnel_data: list[Any] | None = None,
    chapter_code: str | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
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

        section_chart_keys = set(_CHART_RE.findall(body))
        for chart_key in item.get("required_charts") or []:
            if chart_key not in section_chart_keys:
                issues.append(
                    {"code": "missing_required_chart", "section_code": section_code, "chart_key": chart_key, "severity": "P0"}
                )
        for table_spec in item.get("required_tables") or []:
            synonyms = table_spec if isinstance(table_spec, (list, tuple)) else (table_spec,)
            synonyms = tuple(str(s) for s in synonyms if s)
            if not synonyms:
                continue
            if not any(label in body for label in synonyms):
                issues.append(
                    {
                        "code": "missing_required_table",
                        "section_code": section_code,
                        "table_label": synonyms[0],
                        "accepted_synonyms": list(synonyms),
                        "severity": "P0",
                    }
                )

    equipment_placeholders = re.findall(r"\{\{equipment_table:(vehicle|machine|tool|safety)\}\}", content_md or "")
    if equipment_data is not None:
        for asset_type in sorted(set(equipment_placeholders)):
            if not equipment_data.get(asset_type):
                issues.append(
                    {
                        "code": "required_table_empty",
                        "table_key": f"equipment_table:{asset_type}",
                        "severity": "P0",
                    }
                )

    if "{{personnel_table}}" in (content_md or "") and personnel_data is not None and not personnel_data:
        issues.append(
            {
                "code": "required_table_empty",
                "table_key": "personnel_table",
                "severity": "P0",
            }
        )

    expected_chapter = str(chapter_code).strip() if chapter_code else None
    for constraint in constraints:
        metadata = constraint.get("metadata_json") or {}
        critical = constraint.get("confirmation_level") == "critical" or bool(metadata.get("has_conflict"))
        if not critical:
            continue
        mapped_section = str(
            constraint.get("response_section_code")
            or constraint.get("mapped_section_code")
            or metadata.get("response_section_code")
            or metadata.get("mapped_section_code")
            or ""
        ).strip()
        if not mapped_section:
            # Unmapped critical constraints cannot be evaluated per-chapter; skip silently.
            continue
        if expected_chapter:
            mapped_chapter = mapped_section.split(".")[0]
            if mapped_chapter != expected_chapter:
                # Cross-chapter constraint; not this chapter's responsibility.
                continue
        if mapped_section not in present_sections:
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
    if isinstance(asset, Mapping):
        return asset.get(key)
    return getattr(asset, key, None)


def normalize_allowed_chart_keys(recommended_charts: Any, chart_assets: Any) -> set[str]:
    keys: set[str] = set()
    for item in _as_list(recommended_charts):
        _collect_chart_keys(keys, item)
    for item in _as_list(chart_assets):
        _collect_chart_keys(keys, item)
    return keys


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, Mapping)):
        return [value]
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _collect_chart_keys(keys: set[str], item: Any) -> None:
    if isinstance(item, str):
        if item:
            keys.add(item)
        return
    for field in ("placeholder_key", "chart_type"):
        value = _asset_value(item, field)
        if value:
            keys.add(str(value))


def build_chart_closure_report(
    content_md: str,
    *,
    chart_assets: list[Any],
    inserted_chart_keys: list[str] | None = None,
    residual_placeholders: list[str] | None = None,
    allowed_chart_keys: set[str] | list[str] | None = None,
) -> dict[str, Any]:
    referenced = set(_CHART_RE.findall(content_md or ""))
    inserted = set(inserted_chart_keys or [])
    residual = set(residual_placeholders or [])
    allowed = set(allowed_chart_keys or [])
    by_key = {
        str(_asset_value(asset, "placeholder_key") or _asset_value(asset, "chart_type") or ""): asset
        for asset in chart_assets
        if (_asset_value(asset, "placeholder_key") or _asset_value(asset, "chart_type"))
    }
    issues: list[dict[str, Any]] = []
    approved_count = 0
    rendered_count = 0

    for key in sorted(referenced):
        if allowed and key not in allowed:
            issues.append({"code": "chart_key_not_allowed", "chart_key": key, "severity": "P1"})
            continue
        asset = by_key.get(key)
        if not asset:
            issues.append({"code": "missing_chart_asset", "chart_key": key, "severity": "P0"})
        else:
            if _asset_value(asset, "status") == "approved":
                approved_count += 1
            else:
                issues.append({"code": "chart_not_approved", "chart_key": key, "severity": "P0"})
            if (
                _asset_value(asset, "rendered_path")
                or _asset_value(asset, "rendered_svg")
                or _asset_value(asset, "rendered_png_path")
            ):
                rendered_count += 1
            else:
                issues.append({"code": "chart_not_rendered", "chart_key": key, "severity": "P0"})

        if inserted_chart_keys is not None and key not in inserted:
            issues.append({"code": "chart_not_inserted", "chart_key": key, "severity": "P0"})
        if key in residual:
            issues.append({"code": "chart_placeholder_residual", "chart_key": key, "severity": "P0"})

    for key in sorted(residual - referenced):
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
