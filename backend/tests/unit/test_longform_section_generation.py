from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

import pytest

from tender_backend.services.longform_section_generation import (
    LongformSectionGenerator,
    plan_chapter_8_sections,
    plan_chapter_sections,
)
from tender_backend.services.longform_quality import _present_section_codes
from tender_backend.services.technical_chapter_strategies import LONGFORM_SECTION_SETS
from tender_backend.services.technical_chapter_strategies.registry import CHAPTER_8_SECTIONS


class ReviewPriority(Enum):
    HIGH = "high"


def test_plan_chapter_8_sections_creates_8_1_to_8_15_with_page_budget():
    sections = plan_chapter_8_sections(target_pages=100)

    assert [section["section_code"] for section in sections] == [f"8.{index}" for index in range(1, 16)]
    assert sum(section["target_pages"] for section in sections) == 100
    assert all(section["min_chars"] >= 1500 for section in sections)
    assert all(section["min_chars"] <= 2300 for section in sections)
    assert all(section["subsection_density_hint"]["expected_chars"] == section["min_chars"] for section in sections)
    assert all(section["subsection_density_hint"]["expected_subsections"] >= 4 for section in sections)


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


def test_plan_chapter_8_sections_match_registry_codes_and_titles():
    sections = plan_chapter_8_sections(target_pages=100)
    expected = [tuple(heading.split(" ", 1)) for heading, _body in CHAPTER_8_SECTIONS]

    assert [(section["section_code"], section["title"]) for section in sections] == expected


def test_plan_chapter_sections_supports_work_plan_and_10x_chapters():
    chapter_9 = plan_chapter_sections("9", target_pages=40)
    chapter_10_1 = plan_chapter_sections("10.1", target_pages=45)
    chapter_10_2 = plan_chapter_sections("10.2", target_pages=45)
    chapter_10_3 = plan_chapter_sections("10.3", target_pages=45)

    assert [section["section_code"] for section in chapter_9] == [f"9.{index}" for index in range(1, 9)]
    assert chapter_10_1[0]["section_code"] == "10.1.1"
    assert chapter_10_1[-1]["section_code"] == "10.1.15"
    assert chapter_10_2[-1]["section_code"] == "10.2.16"
    assert chapter_10_3[-1]["section_code"] == "10.3.15"
    assert any("quality_system" in section["required_charts"] for section in chapter_10_1)
    assert any("safety_system" in section["required_charts"] for section in chapter_10_2)
    assert any("schedule_gantt" in section["required_charts"] for section in chapter_10_3)


def test_plan_chapter_sections_match_registry_numbering_and_heading_regex():
    for chapter_code, section_set in LONGFORM_SECTION_SETS.items():
        target_pages = max(80 if chapter_code == "8" else 40, len(section_set))
        planned = plan_chapter_sections(chapter_code, target_pages=target_pages)
        expected_codes = [heading.split(" ", 1)[0] for heading, _body in section_set]

        assert [section["section_code"] for section in planned] == expected_codes
        content_md = "\n\n".join(f"### {section['section_code']} {section['title']}\n\n正文" for section in planned)
        assert _present_section_codes(content_md) == set(expected_codes)


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
    assert calls[0]["subsection_density_hint"]["expected_chars"] == 20
    assert calls[0]["subsection_density_hint"]["expected_subsections"] >= 4
    assert result["status"] == "completed"
    assert result["sections"][0]["continuation_rounds"] == 2
    assert "## 8.1 编制依据" in result["content_md"]


def test_generator_passes_planned_chapter_code_to_completion_payload():
    calls = []

    def fake_completion(payload):
        calls.append(payload)
        return {"content": "足够内容" * 10, "metadata": {}}

    generator = LongformSectionGenerator(completion_fn=fake_completion, max_rounds=1)
    result = generator.generate_sections(
        context={"chapter": {"chapter_code": "10.1"}},
        section_plan=[
            {
                "chapter": "10.1",
                "section_code": "10.1.3",
                "title": "质量保证体系与组织职责",
                "target_pages": 2,
                "min_chars": 10,
                "required_charts": ["quality_system"],
                "required_tables": [],
            }
        ],
    )

    assert result["status"] == "completed"
    assert calls[0]["chapter"] == "10.1"
    assert calls[0]["section_code"] == "10.1.3"


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


def test_generator_defaults_to_six_rounds() -> None:
    generator = LongformSectionGenerator(completion_fn=lambda _payload: {"content": "", "metadata": {}})

    assert generator.max_rounds == 6


def test_generator_breaks_after_two_low_value_continuation_rounds() -> None:
    calls = []

    def fake_completion(payload):
        calls.append(payload)
        return {"content": "短", "metadata": {}}

    generator = LongformSectionGenerator(completion_fn=fake_completion, max_rounds=6)
    result = generator.generate_sections(
        context={},
        section_plan=[
            {
                "section_code": "8.1",
                "title": "编制依据",
                "target_pages": 1,
                "min_chars": 1000,
                "required_charts": [],
                "required_tables": [],
            }
        ],
    )

    assert len(calls) == 2
    assert result["status"] == "failed"
    assert result["sections"][0]["status"] == "failed_min_chars"
    assert result["sections"][0]["continuation_rounds"] == 2
    assert result["sections"][0]["low_value_rounds"] == 2


def test_generator_switches_to_premium_task_for_underfilled_continuation_round() -> None:
    task_types = []

    def fake_completion(payload):
        task_types.append(payload["task"])
        if payload["round_index"] == 1:
            return {"content": "首轮内容" * 20, "metadata": {}}
        return {"content": "补充内容" * 600, "metadata": {}}

    generator = LongformSectionGenerator(completion_fn=fake_completion, max_rounds=3, premium_threshold_chars=2200)
    result = generator.generate_sections(
        context={},
        section_plan=[
            {
                "section_code": "8.4",
                "title": "主要施工方法及技术要求",
                "target_pages": 10,
                "min_chars": 2300,
                "required_charts": [],
                "required_tables": [],
            }
        ],
    )

    assert task_types == ["generate_longform_subsection", "generate_longform_subsection_premium"]
    assert result["sections"][0]["used_premium_rounds"] == 1


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
