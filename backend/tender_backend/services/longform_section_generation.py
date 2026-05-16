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
    "编制依据",
    "工程概况",
    "施工总体部署",
    "施工进度计划",
    "施工准备与资源配置",
    "主要施工方法与技术措施",
    "施工现场平面布置",
    "质量管理体系与保证措施",
    "安全生产管理体系与保证措施",
    "文明施工与环境保护措施",
    "工期保证措施",
    "重点难点分析及应对措施",
    "季节性施工措施",
    "成品保护与交付配合",
    "应急预案与风险控制",
]

_DEFAULT_CHARTS: dict[str, list[str]] = {
    "8.3": ["construction_flow"],
    "8.4": ["schedule_gantt"],
    "8.7": ["schedule_gantt"],
    "8.8": ["quality_system"],
    "8.9": ["safety_system"],
    "8.12": ["risk_matrix"],
}

_DEFAULT_TABLES: dict[str, list[str]] = {
    "8.2": ["工程概况表"],
    "8.5": ["资源配置计划表"],
    "8.6": ["主要施工方法表"],
    "8.8": ["质量控制点表"],
    "8.9": ["安全风险管控表"],
    "8.11": ["工期保证措施表"],
    "8.12": ["重点难点应对表"],
}

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _weighted_text_units(content_md: str) -> int:
    chinese_chars = len(_CHINESE_RE.findall(content_md or ""))
    western_words = len(_WORD_RE.findall(content_md or ""))
    return chinese_chars + math.ceil(western_words * 1.8)


def plan_chapter_8_sections(*, target_pages: int) -> list[dict[str, Any]]:
    """Create the 15-section chapter 8 plan with an exact page budget."""

    section_count = len(_CHAPTER_8_TITLES)
    if target_pages < section_count:
        raise ValueError(f"target_pages must be at least {section_count}")

    base_pages, extra_pages = divmod(target_pages, section_count)
    sections: list[dict[str, Any]] = []

    for index, title in enumerate(_CHAPTER_8_TITLES, start=1):
        section_code = f"8.{index}"
        pages = base_pages + (1 if index <= extra_pages else 0)
        sections.append(
            {
                "chapter": "8",
                "section_code": section_code,
                "title": title,
                "target_pages": pages,
                "min_chars": max(2800, pages * 620),
                "required_charts": list(_DEFAULT_CHARTS.get(section_code, [])),
                "required_tables": list(_DEFAULT_TABLES.get(section_code, [])),
            }
        )

    return sections


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

    def __init__(self, completion_fn: Callable[[dict], dict], max_rounds: int = 4):
        if max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        self.completion_fn = completion_fn
        self.max_rounds = max_rounds

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
            required_charts = list(planned.get("required_charts") or [])
            required_tables = list(planned.get("required_tables") or [])
            generated = ""
            prompt_hash = ""
            rounds = 0

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
                payload = {
                    "task": "generate_longform_subsection",
                    "chapter": "8",
                    "section_code": section_code,
                    "section_title": title,
                    "target_pages": target_pages,
                    "min_chars": min_chars,
                    "required_charts": required_charts,
                    "required_tables": required_tables,
                    "round_index": round_index,
                    "existing_content_tail": generated[-1000:],
                    "context": context,
                }
                if round_index == 1:
                    prompt_hash = _stable_sha256(payload)

                completion = self.completion_fn(payload)
                rounds = round_index
                piece = _completion_content(completion)
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
                    "actual_chars": weighted_chars,
                    "status": status,
                    "continuation_rounds": rounds,
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
