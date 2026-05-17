"""Subsection planning and continuation loop for longform chapter 8."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from typing import Any

from tender_backend.services.longform_quality import estimate_markdown_pages

_CHAPTER_8_TITLES = [
    "编制依据与标准",
    "工程概况与施工重难点分析",
    "施工组织与部署",
    "主要施工方法及技术要求",
    "质量管理体系与措施",
    "安全管理体系与措施",
    "施工进度计划与保障",
    "环境保护、绿色低碳与碳足迹管理",
    "科技创新与智能化应用",
    "地域特性专题方案",
    "竣工验收与数字化移交",
    "售后服务、培训及增值服务",
    "拟投入施工车辆、机具、工器具、检测设备、安全工器具及设施",
    "施工项目部组织架构创新设计",
    "国网年度框架施工工程投标其他创新内容",
]

_DEFAULT_CHARTS: dict[str, list[str]] = {
    "8.1": ["response_matrix"],
    "8.2": ["risk_matrix"],
    "8.3": ["construction_flow"],
    "8.4": ["construction_flow"],
    "8.5": ["quality_system"],
    "8.6": ["safety_system", "risk_matrix"],
    "8.7": ["schedule_gantt"],
    "8.11": ["closure_flow"],
    "8.13": ["equipment_table"],
}

_DEFAULT_TABLES: dict[str, tuple[tuple[str, ...], ...]] = {
    "8.1": (("响应矩阵", "标准响应矩阵", "条款响应矩阵"),),
    "8.2": (("工程概况表", "工程概况一览表", "项目概况表", "重难点分析表", "重点难点分析表"),),
    "8.4": (("主要施工方法表", "主要施工方法清单", "主要施工工序表", "施工方法表"),),
    "8.5": (("质量控制点表", "WHS控制点表", "质量控制点清单", "WHSR控制点表", "质量控制清单"),),
    "8.6": (("安全风险管控表", "危险源辨识与分级管控表", "风险分级管控清单", "危险源辨识与管控表"),),
    "8.7": (("工期保证措施表", "进度保证措施表", "关键工期保证表"),),
    "8.13": (("设备清单", "设备配置表", "施工设备表", "拟投入设备表"),),
}

# Section weight allocation for min_chars per section title (sum=15.5).
# High weight: 8.4 main methods, 8.5 quality system, 8.6 safety, 8.7 schedule.
# Low weight: 8.1 basis, 8.13 equipment list, 8.14 org chart, 8.15 innovation.
_SECTION_WEIGHTS: dict[str, float] = {
    "8.1": 0.6,
    "8.2": 1.3,
    "8.3": 1.2,
    "8.4": 1.8,
    "8.5": 1.5,
    "8.6": 1.5,
    "8.7": 1.4,
    "8.8": 1.0,
    "8.9": 0.9,
    "8.10": 1.0,
    "8.11": 1.0,
    "8.12": 0.7,
    "8.13": 0.6,
    "8.14": 0.6,
    "8.15": 0.5,
}

# 380 chars/page reflects actual docx Chinese density (was 620, too high)
# Cap=2300 ≈ 6 pages: empirically aligns with single-chapter LLM output ceiling
# (deepseek-v4-flash 32k max_tokens but ~2000~2800 chars per round for Chinese
# after subtracting markdown structure).
_CHARS_PER_PAGE = 380
_MIN_CHARS_FLOOR = 1500
_MIN_CHARS_CAP = 2300

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _weighted_text_units(content_md: str) -> int:
    chinese_chars = len(_CHINESE_RE.findall(content_md or ""))
    western_words = len(_WORD_RE.findall(content_md or ""))
    return chinese_chars + math.ceil(western_words * 1.8)


def plan_chapter_8_sections(*, target_pages: int) -> list[dict[str, Any]]:
    """Create the 15-section chapter 8 plan with weighted page budget."""

    section_count = len(_CHAPTER_8_TITLES)
    if target_pages < section_count:
        raise ValueError(f"target_pages must be at least {section_count}")

    weight_sum = sum(_SECTION_WEIGHTS.values())
    pages_per_weight = target_pages / weight_sum

    # First pass: raw float pages per section
    raw_pages = []
    for index in range(1, section_count + 1):
        section_code = f"8.{index}"
        weight = _SECTION_WEIGHTS.get(section_code, 1.0)
        raw_pages.append(weight * pages_per_weight)

    # Second pass: floor each to int (min 1), then distribute remainder to
    # sections with the largest fractional remainder so that the total exactly
    # matches target_pages.
    floor_pages = [max(1, int(value)) for value in raw_pages]
    remainder = target_pages - sum(floor_pages)
    fractional_order = sorted(
        range(len(raw_pages)),
        key=lambda i: -(raw_pages[i] - int(raw_pages[i])),
    )
    for i in fractional_order[: max(0, remainder)]:
        floor_pages[i] += 1

    sections: list[dict[str, Any]] = []
    for index, title in enumerate(_CHAPTER_8_TITLES, start=1):
        section_code = f"8.{index}"
        weight = _SECTION_WEIGHTS.get(section_code, 1.0)
        pages = floor_pages[index - 1]
        min_chars = max(
            _MIN_CHARS_FLOOR,
            min(_MIN_CHARS_CAP, int(weight * pages_per_weight * _CHARS_PER_PAGE)),
        )
        density_hint = _subsection_density_hint(min_chars=min_chars, target_pages=pages, weight=weight)
        sections.append(
            {
                "chapter": "8",
                "section_code": section_code,
                "title": title,
                "target_pages": pages,
                "min_chars": min_chars,
                "subsection_density_hint": density_hint,
                "required_charts": list(_DEFAULT_CHARTS.get(section_code, [])),
                "required_tables": [list(synonyms) for synonyms in _DEFAULT_TABLES.get(section_code, ())],
            }
        )

    return sections


def _subsection_density_hint(*, min_chars: int, target_pages: int, weight: float | None = None) -> dict[str, int | float]:
    expected_subsections = max(4, min(9, math.ceil(min_chars / 420)))
    expected_paragraphs = max(expected_subsections * 2, math.ceil(min_chars / 180))
    return {
        "expected_chars": min_chars,
        "expected_paragraphs": expected_paragraphs,
        "expected_subsections": expected_subsections,
        "target_pages": target_pages,
        "section_weight": float(weight or 1.0),
    }


def _json_hashable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_hashable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_hashable(item) for item in value]
    return value


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        _json_hashable(payload),
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _completion_content(completion: dict[str, Any]) -> str:
    return str(completion.get("content") or completion.get("content_md") or completion.get("text") or "")


def _completion_metadata(completion: dict[str, Any]) -> dict[str, Any]:
    metadata = completion.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return completion


def _int_metadata(metadata: dict[str, Any], key: str) -> int:
    value = metadata.get(key, 0)
    if value is None:
        return 0
    return int(value)


class LongformSectionGenerator:
    """Generate planned subsections, continuing until each reaches its character floor."""

    def __init__(self, completion_fn: Callable[[dict], dict], max_rounds: int = 6, premium_threshold_chars: int = 2200):
        if max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        self.completion_fn = completion_fn
        self.max_rounds = max_rounds
        self.premium_threshold_chars = premium_threshold_chars

    def generate_sections(
        self,
        context: dict,
        section_plan: list[dict],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict:
        content_parts: list[str] = []
        section_results: list[dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_latency_ms = 0

        for planned in section_plan:
            section_code = str(planned["section_code"])
            title = str(planned.get("title") or planned.get("section_title") or "")
            target_pages = int(planned.get("target_pages") or 0)
            min_chars = int(planned.get("min_chars") or 0)
            density_hint = dict(
                planned.get("subsection_density_hint")
                or _subsection_density_hint(min_chars=min_chars, target_pages=target_pages)
            )
            required_charts = list(planned.get("required_charts") or [])
            required_tables = list(planned.get("required_tables") or [])
            generated = ""
            prompt_hash = ""
            rounds = 0
            low_value_rounds = 0
            used_premium_rounds = 0

            previous_outlines = [
                {
                    "section_code": r["section_code"],
                    "title": r["title"],
                    "actual_chars": r["actual_chars"],
                    "status": r["status"],
                }
                for r in section_results
            ]

            for round_index in range(1, self.max_rounds + 1):
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "round_started",
                            "section_code": section_code,
                            "title": title,
                            "round_index": round_index,
                            "max_rounds": self.max_rounds,
                            "completed_sections": len(section_results),
                            "total_sections": len(section_plan),
                            "content_md": f"## {section_code} {title}\n\n{generated}".rstrip(),
                            "percent": int(((len(section_results) + (round_index - 1) / self.max_rounds) / max(len(section_plan), 1)) * 100),
                        }
                    )
                use_premium = round_index >= 2 and _weighted_text_units(generated) < self.premium_threshold_chars
                if use_premium:
                    used_premium_rounds += 1
                payload = {
                    "task": "generate_longform_subsection_premium" if use_premium else "generate_longform_subsection",
                    "chapter": "8",
                    "section_code": section_code,
                    "section_title": title,
                    "target_pages": target_pages,
                    "min_chars": min_chars,
                    "subsection_density_hint": density_hint,
                    "required_charts": required_charts,
                    "required_tables": required_tables,
                    "round_index": round_index,
                    "existing_content_tail": generated[-3000:],
                    "current_char_count": _weighted_text_units(generated),
                    "previous_section_outlines": previous_outlines,
                    "context": context,
                }
                if round_index == 1:
                    prompt_hash = _stable_sha256(payload)

                completion = self.completion_fn(payload)
                rounds = round_index
                piece = _completion_content(completion)
                if _weighted_text_units(piece) < 100:
                    low_value_rounds += 1
                else:
                    low_value_rounds = 0
                generated = f"{generated}\n\n{piece}".strip() if generated and piece else generated + piece

                metadata = _completion_metadata(completion)
                total_input_tokens += _int_metadata(metadata, "input_tokens")
                total_output_tokens += _int_metadata(metadata, "output_tokens")
                total_latency_ms += _int_metadata(metadata, "latency_ms")

                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "round_progress",
                            "section_code": section_code,
                            "title": title,
                            "round_index": round_index,
                            "max_rounds": self.max_rounds,
                            "completed_sections": len(section_results),
                            "total_sections": len(section_plan),
                            "content_md": f"## {section_code} {title}\n\n{generated}".rstrip(),
                            "percent": int(((len(section_results) + round_index / self.max_rounds) / max(len(section_plan), 1)) * 100),
                        }
                    )

                if _weighted_text_units(generated) >= min_chars:
                    break
                if low_value_rounds >= 2:
                    break

            weighted_chars = _weighted_text_units(generated)
            status = "completed" if weighted_chars >= min_chars else "failed_min_chars"
            section_md = f"## {section_code} {title}\n\n{generated}".rstrip()
            content_parts.append(section_md)
            page_estimate = estimate_markdown_pages(section_md, target_pages=target_pages)
            section_results.append(
                {
                    "section_code": section_code,
                    "title": title,
                    "target_pages": target_pages,
                    "min_chars": min_chars,
                    "subsection_density_hint": density_hint,
                    "actual_chars": weighted_chars,
                    "status": status,
                    "continuation_rounds": rounds,
                    "low_value_rounds": low_value_rounds,
                    "used_premium_rounds": used_premium_rounds,
                    "required_charts": required_charts,
                    "required_tables": required_tables,
                    "prompt_hash": prompt_hash,
                    "page_estimate": page_estimate,
                }
            )
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "section_completed",
                        "section_code": section_code,
                        "title": title,
                        "round_index": rounds,
                        "max_rounds": self.max_rounds,
                        "completed_sections": len(section_results),
                        "total_sections": len(section_plan),
                        "content_md": "\n\n".join(content_parts),
                        "section_result": section_results[-1],
                        "percent": int((len(section_results) / max(len(section_plan), 1)) * 100),
                    }
                )

        content_md = "\n\n".join(content_parts)
        overall_status = "completed" if all(section["status"] == "completed" for section in section_results) else "failed"

        return {
            "status": overall_status,
            "content_md": content_md,
            "sections": section_results,
            "metadata": {
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "latency_ms": total_latency_ms,
                "max_rounds": self.max_rounds,
                "section_count": len(section_plan),
                "page_estimate": estimate_markdown_pages(content_md, target_pages=sum(int(s.get("target_pages") or 0) for s in section_plan)),
            },
        }
