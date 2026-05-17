"""Non-blocking SVG quality checks for rendered chart assets."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from tender_backend.services.chart_service.templates import ChartTemplate
from tender_backend.services.chart_service.visual_template import FONT, PAGE


_FONT_FAMILIES_AVAILABLE = {
    "noto sans cjk sc",
    "noto sans cjk",
    "microsoft yahei",
    "simsun",
    "sans-serif",
}


def evaluate_svg_quality(svg: str, template: ChartTemplate) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    root = _parse_svg(svg)
    text_nodes = _text_nodes(root)
    text_rules = template.text_rules
    density_limits = template.density_limits

    node_chars = int(text_rules.get("node_chars") or text_rules.get("cell_chars") or text_rules.get("task_chars") or 0)
    overflow_count = 0
    if node_chars > 0:
        for value in text_nodes:
            if len(value["text"]) > node_chars:
                overflow_count += 1
                issues.append({"code": "text_overflow", "text": value["text"], "limit": node_chars})

    aspect_ratio = _aspect_ratio(root, svg)
    if aspect_ratio is not None and (aspect_ratio > 5 or aspect_ratio < 0.2):
        issues.append({"code": "aspect_extreme", "aspect_ratio": round(aspect_ratio, 3)})

    max_nodes = int(density_limits.get("max_nodes") or 0)
    if max_nodes > 0 and len(text_nodes) > max_nodes * 2:
        issues.append({"code": "density_overload", "text_count": len(text_nodes), "limit": max_nodes * 2})

    min_font_px = int(text_rules.get("min_font_px") or 0)
    if min_font_px > 0:
        for value in text_nodes:
            font_size = value.get("font_size")
            if font_size is not None and font_size < min_font_px:
                issues.append({"code": "font_below_minimum", "font_size": font_size, "limit": min_font_px})

    metrics, metric_issues = _quantitative_metrics(
        root=root,
        svg=svg,
        text_nodes=text_nodes,
        text_node_char_limit=node_chars,
        text_overflow_count=overflow_count,
        aspect_ratio=aspect_ratio,
        template=template,
    )
    issues.extend(metric_issues)

    return {
        "passed": not issues,
        "issues": issues,
        "metrics": metrics,
    }


def _quantitative_metrics(
    *,
    root: ET.Element | None,
    svg: str,
    text_nodes: list[dict[str, Any]],
    text_node_char_limit: int,
    text_overflow_count: int,
    aspect_ratio: float | None,
    template: ChartTemplate,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}

    total_text = len(text_nodes)
    overflow_rate = (text_overflow_count / total_text) if total_text else 0.0
    metrics["text_overflow_rate"] = round(overflow_rate, 4)
    if total_text and overflow_rate >= 0.02 and text_node_char_limit > 0:
        issues.append(
            {
                "code": "text_overflow_rate",
                "rate": round(overflow_rate, 4),
                "limit": 0.02,
            }
        )

    font_sizes = [value["font_size"] for value in text_nodes if value.get("font_size") is not None]
    min_font = min(font_sizes) if font_sizes else None
    metrics["min_font_px"] = min_font
    if min_font is not None and min_font < FONT.min_px:
        issues.append({"code": "font_below_floor", "font_size": min_font, "limit": FONT.min_px})

    metrics["aspect_ratio"] = round(aspect_ratio, 4) if aspect_ratio is not None else None
    if template.layout_family == "matrix" and aspect_ratio is not None:
        if aspect_ratio > PAGE.matrix_max_aspect_ratio or aspect_ratio < PAGE.matrix_min_aspect_ratio:
            issues.append(
                {
                    "code": "matrix_aspect_out_of_range",
                    "aspect_ratio": round(aspect_ratio, 3),
                    "min": PAGE.matrix_min_aspect_ratio,
                    "max": PAGE.matrix_max_aspect_ratio,
                }
            )

    viewbox_width = _viewbox_width(root, svg)
    # docx_dpi = svg_viewbox_width × png_zoom / docx_image_width_inches。
    # png_converter.svg_to_png 当前默认 zoom=2.0，光栅化后宽度翻倍。
    docx_dpi = (viewbox_width * 2.0 / PAGE.docx_image_width_in) if viewbox_width else None
    metrics["docx_dpi"] = round(docx_dpi, 1) if docx_dpi is not None else None
    if docx_dpi is not None and docx_dpi < 96:
        issues.append({"code": "docx_dpi_below_floor", "dpi": round(docx_dpi, 1), "limit": 96})

    font_families = _font_families(text_nodes, root)
    unknown_families = sorted(
        family
        for family in font_families
        if not any(known in family.lower() for known in _FONT_FAMILIES_AVAILABLE)
    )
    metrics["font_families"] = sorted(font_families)
    metrics["unknown_font_families"] = unknown_families
    if unknown_families:
        issues.append({"code": "font_family_unavailable", "families": unknown_families})

    return metrics, issues


def _parse_svg(svg: str) -> ET.Element | None:
    try:
        return ET.fromstring(svg)
    except ET.ParseError:
        return None


def _text_nodes(root: ET.Element | None) -> list[dict[str, Any]]:
    if root is None:
        return []
    nodes: list[dict[str, Any]] = []
    for element in root.iter():
        if _local_name(element.tag) != "text":
            continue
        text = "".join(element.itertext()).strip()
        nodes.append(
            {
                "text": text,
                "font_size": _font_size(element.get("font-size")),
                "font_family": element.get("font-family"),
            }
        )
    return nodes


def _aspect_ratio(root: ET.Element | None, svg: str) -> float | None:
    view_box = root.get("viewBox") if root is not None else None
    if view_box:
        numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", view_box)]
        if len(numbers) == 4 and numbers[3] > 0:
            return numbers[2] / numbers[3]
    width = _dimension(root.get("width") if root is not None else None)
    height = _dimension(root.get("height") if root is not None else None)
    if width and height:
        return width / height
    match = re.search(r"viewBox=['\"]([^'\"]+)['\"]", svg)
    if not match:
        return None
    numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", match.group(1))]
    if len(numbers) == 4 and numbers[3] > 0:
        return numbers[2] / numbers[3]
    return None


def _viewbox_width(root: ET.Element | None, svg: str) -> float | None:
    view_box = root.get("viewBox") if root is not None else None
    if view_box:
        numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", view_box)]
        if len(numbers) == 4:
            return numbers[2]
    width = _dimension(root.get("width") if root is not None else None)
    if width:
        return width
    match = re.search(r"viewBox=['\"]([^'\"]+)['\"]", svg)
    if not match:
        return None
    numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", match.group(1))]
    if len(numbers) == 4:
        return numbers[2]
    return None


def _font_families(text_nodes: list[dict[str, Any]], root: ET.Element | None) -> set[str]:
    families: set[str] = set()
    for value in text_nodes:
        family = value.get("font_family")
        if family:
            families.update(_split_font_family(family))
    if root is not None:
        # Also inspect any `style` attribute on style/text or root for fallback declarations.
        root_family = root.get("font-family")
        if root_family:
            families.update(_split_font_family(root_family))
    return families


def _split_font_family(value: str) -> list[str]:
    parts = [part.strip().strip("'\"") for part in value.split(",")]
    return [part for part in parts if part]


def _font_size(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def _dimension(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
