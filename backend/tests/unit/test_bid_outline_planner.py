from __future__ import annotations

from uuid import uuid4

from tender_backend.services.bid_outline_planner import plan_bid_outline_from_requirements


def _requirement(category: str, **overrides):
    row = {
        "id": uuid4(),
        "category": category,
        "title": f"{category} 要求",
        "requirement_text": f"{category} 响应内容",
        "review_status": "pending",
        "ignored_for_pricing": False,
        "is_veto": category == "veto",
        "is_hard_constraint": False,
        "source_locator": "page:1:block:1",
    }
    row.update(overrides)
    return row


def test_plan_bid_outline_creates_required_volumes_and_chapters() -> None:
    project_id = uuid4()
    outline = plan_bid_outline_from_requirements(
        project_id=project_id,
        requirements=[
            _requirement("qualification"),
            _requirement("business"),
            _requirement("technical"),
        ],
    )

    volume_types = {chapter["volume_type"] for chapter in outline["chapters"]}

    assert volume_types == {"qualification", "business", "technical"}
    assert outline["metadata_json"]["priority_policy"] == "tender_extracted_requirements_override_template"
    assert any(chapter["chapter_code"] == "1.1" for chapter in outline["chapters"])
    assert any(chapter["chapter_code"] == "2.2" for chapter in outline["chapters"])
    assert any(chapter["chapter_code"] == "3.1" for chapter in outline["chapters"])


def test_plan_bid_outline_maps_hard_scoring_and_special_requirements() -> None:
    veto = _requirement("veto")
    scoring = _requirement("scoring")
    special = _requirement("special")
    hard = _requirement("format", is_hard_constraint=True)
    ignored = _requirement("pricing", ignored_for_pricing=True)

    outline = plan_bid_outline_from_requirements(
        project_id=uuid4(),
        requirements=[veto, scoring, special, hard, ignored],
    )

    mappings_by_code = {
        chapter["chapter_code"]: {mapping["requirement_id"] for mapping in chapter["requirement_mappings"]}
        for chapter in outline["chapters"]
    }
    all_mapped_ids = set().union(*mappings_by_code.values())

    assert veto["id"] in mappings_by_code["3.3"]
    assert scoring["id"] in mappings_by_code["3.2"]
    assert special["id"] in mappings_by_code["3.4"]
    assert hard["id"] in mappings_by_code["3.3"]
    assert ignored["id"] not in all_mapped_ids
    assert outline["metadata_json"]["unmapped_hard_requirement_ids"] == []


def test_chapter_outline_lists_input_requirements() -> None:
    requirement = _requirement("project_team", title="项目经理须提供证书")

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[requirement])
    chapter = next(item for item in outline["chapters"] if item["chapter_code"] == "1.3")

    assert "项目经理须提供证书" in chapter["outline_md"]
    assert "招标文件 AI 解析结果为最高优先级" in chapter["outline_md"]
