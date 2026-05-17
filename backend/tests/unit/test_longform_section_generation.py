from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

import pytest

from tender_backend.services.longform_section_generation import (
    LongformSectionGenerator,
    plan_chapter_8_sections,
)


class ReviewPriority(Enum):
    HIGH = "high"


def test_plan_chapter_8_sections_creates_8_1_to_8_15_with_page_budget():
    sections = plan_chapter_8_sections(target_pages=100)

    assert [section["section_code"] for section in sections] == [f"8.{index}" for index in range(1, 16)]
    assert sum(section["target_pages"] for section in sections) == 100
    assert all(section["min_chars"] >= 1500 for section in sections)
    assert all(section["min_chars"] <= 2300 for section in sections)


def test_plan_chapter_8_sections_weights_high_priority_sections_higher():
    sections = plan_chapter_8_sections(target_pages=100)
    by_code = {section["section_code"]: section for section in sections}
    # 8.4 main construction methods should be the heaviest section under the new
    # numbering aligned with CHAPTER_8_SECTIONS (registry).
    assert by_code["8.4"]["min_chars"] > by_code["8.14"]["min_chars"]
    assert by_code["8.5"]["min_chars"] > by_code["8.1"]["min_chars"]


def test_plan_chapter_8_sections_required_tables_are_synonym_lists():
    sections = plan_chapter_8_sections(target_pages=100)
    by_code = {section["section_code"]: section for section in sections}
    tables = by_code["8.5"]["required_tables"]
    assert tables and isinstance(tables[0], list)
    assert "质量控制点表" in tables[0]
    assert "WHS控制点表" in tables[0]


@pytest.mark.parametrize("target_pages", [0, 14])
def test_plan_chapter_8_sections_rejects_incoherent_page_budgets(target_pages):
    with pytest.raises(ValueError, match="target_pages must be at least 15"):
        plan_chapter_8_sections(target_pages=target_pages)


def test_generator_continues_until_section_meets_min_chars():
    calls = []

    def fake_completion(payload):
        calls.append(payload)
        if payload["round_index"] == 1:
            return {"content": "太短", "metadata": {"input_tokens": 5, "output_tokens": 6, "latency_ms": 7}}
        return {"content": "足够内容" * 20, "metadata": {"input_tokens": 8, "output_tokens": 9, "latency_ms": 10}}

    generator = LongformSectionGenerator(completion_fn=fake_completion, max_rounds=3)
    result = generator.generate_sections(
        context={"project": "测试项目"},
        section_plan=[
            {
                "section_code": "8.1",
                "title": "编制依据",
                "target_pages": 1,
                "min_chars": 20,
                "required_charts": [],
                "required_tables": [],
            }
        ],
    )

    assert len(calls) == 2
    assert result["status"] == "completed"
    assert result["sections"][0]["continuation_rounds"] == 2
    assert "## 8.1 编制依据" in result["content_md"]


def test_generate_sections_succeeds_and_hashes_prompt_with_common_non_json_context_values():
    calls = []

    def fake_completion(payload):
        calls.append(payload)
        return {"content": "足够内容" * 10, "metadata": {}}

    generator = LongformSectionGenerator(completion_fn=fake_completion, max_rounds=1)
    result = generator.generate_sections(
        context={
            "project_id": UUID("12345678-1234-5678-1234-567812345678"),
            "deadline": datetime(2026, 5, 15, 9, 30, tzinfo=timezone.utc),
            "budget": Decimal("12.34"),
            "priority": ReviewPriority.HIGH,
            7: "mixed non-string key",
        },
        section_plan=[
            {
                "section_code": "8.1",
                "title": "编制依据",
                "target_pages": 1,
                "min_chars": 10,
                "required_charts": [],
                "required_tables": [],
            }
        ],
    )

    assert calls
    assert result["status"] == "completed"
    assert len(result["sections"][0]["prompt_hash"]) == 64


def test_generator_marks_section_failed_after_max_rounds():
    def fake_completion(payload):
        return {"content": "太短", "metadata": {}}

    generator = LongformSectionGenerator(completion_fn=fake_completion, max_rounds=2)
    result = generator.generate_sections(
        context={},
        section_plan=[
            {
                "section_code": "8.1",
                "title": "编制依据",
                "target_pages": 1,
                "min_chars": 100,
                "required_charts": [],
                "required_tables": [],
            }
        ],
    )

    assert result["status"] == "failed"
    assert result["sections"][0]["status"] == "failed_min_chars"
    assert result["sections"][0]["continuation_rounds"] == 2


def test_generator_keeps_subsection_order_and_metadata():
    def fake_completion(payload):
        return {"content": f"{payload['section_code']}内容" * 20, "metadata": {"output_tokens": 20}}

    generator = LongformSectionGenerator(completion_fn=fake_completion, max_rounds=1)
    result = generator.generate_sections(
        context={"project": "测试项目"},
        section_plan=[
            {
                "section_code": "8.1",
                "title": "编制依据",
                "target_pages": 1,
                "min_chars": 10,
                "required_charts": ["basis_map"],
                "required_tables": [],
            },
            {
                "section_code": "8.2",
                "title": "工程概况",
                "target_pages": 1,
                "min_chars": 10,
                "required_charts": ["site_plan"],
                "required_tables": ["工程概况表"],
            },
        ],
    )

    assert result["status"] == "completed"
    assert result["content_md"].index("## 8.1 编制依据") < result["content_md"].index("## 8.2 工程概况")
    assert result["sections"][0]["required_charts"] == ["basis_map"]
    assert result["sections"][1]["required_charts"] == ["site_plan"]
    assert result["metadata"]["total_output_tokens"] == 40


def test_generator_reports_round_progress_before_section_completion():
    progress_events = []

    def fake_completion(payload):
        if payload["round_index"] == 1:
            return {"content": "首轮内容", "metadata": {"input_tokens": 1, "output_tokens": 2, "latency_ms": 3}}
        return {"content": "补充内容" * 10, "metadata": {"input_tokens": 4, "output_tokens": 5, "latency_ms": 6}}

    generator = LongformSectionGenerator(completion_fn=fake_completion, max_rounds=2)
    result = generator.generate_sections(
        context={"project": "测试项目"},
        section_plan=[
            {
                "section_code": "8.1",
                "title": "编制依据",
                "target_pages": 1,
                "min_chars": 20,
                "required_charts": [],
                "required_tables": [],
            }
        ],
        progress_callback=lambda payload: progress_events.append(payload),
    )

    assert result["status"] == "completed"
    assert progress_events[0]["event"] == "round_started"
    assert progress_events[0]["round_index"] == 1
    assert progress_events[0]["completed_sections"] == 0
    assert progress_events[0]["percent"] == 0
    assert progress_events[1]["event"] == "round_progress"
    assert "首轮内容" in progress_events[1]["content_md"]
    assert progress_events[-1]["event"] == "section_completed"
    assert progress_events[-1]["completed_sections"] == 1
