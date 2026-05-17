"""Non-blocking SVG quality checks for rendered chart assets."""

from __future__ import annotations

import re
from typing import Any
import xml.etree.ElementTree as ET

from tender_backend.services.chart_service.templates import ChartTemplate


def evaluate_svg_quality(svg: str, template: ChartTemplate) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    root = _parse_svg(svg)
    text_nodes = _text_nodes(root)
    text_rules = template.text_rules
    density_limits = template.density_limits

    node_chars = int(text_rules.get("node_chars") or text_rules.get("cell_chars") or text_rules.get("task_chars") or 0)
    if node_chars > 0:
        for value in text_nodes:
            if len(value["text"]) > node_chars:
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

    return {"passed": not issues, "issues": issues}


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
        nodes.append({"text": text, "font_size": _font_size(element.get("font-size"))})
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
