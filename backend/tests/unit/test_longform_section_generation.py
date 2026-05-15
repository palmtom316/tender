from tender_backend.services.longform_section_generation import (
    LongformSectionGenerator,
    plan_chapter_8_sections,
)


def test_plan_chapter_8_sections_creates_8_1_to_8_15_with_page_budget():
    sections = plan_chapter_8_sections(target_pages=100)

    assert [section["section_code"] for section in sections] == [f"8.{index}" for index in range(1, 16)]
    assert sum(section["target_pages"] for section in sections) == 100
    assert all(section["min_chars"] >= 2800 for section in sections)


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
