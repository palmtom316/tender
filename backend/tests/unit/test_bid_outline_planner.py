from __future__ import annotations

from uuid import uuid4

from tender_backend.services.bid_outline_planner import (
    build_bid_outline,
    plan_bid_outline_from_confirmed_constraints,
    plan_bid_outline_from_requirements,
)
from tender_backend.services.bid_outline_templates import base_bid_chapters


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
    assert any(chapter["chapter_code"] == "1" and chapter["chapter_title"] == "商务偏差表" for chapter in outline["chapters"])
    assert any(chapter["chapter_code"] == "24.8" and chapter["chapter_title"] == "其他" for chapter in outline["chapters"])
    assert any(chapter["chapter_code"] == "8" and chapter["chapter_title"] == "施工方案与技术措施" for chapter in outline["chapters"])
    assert any(chapter["chapter_code"] == "8.15" and chapter["chapter_title"] == "国网年度框架施工工程投标其他创新内容" for chapter in outline["chapters"])
    assert outline["metadata_json"]["business_outline_template_key"] == "sgcc_distribution_business_v1"
    assert outline["metadata_json"]["technical_outline_template_key"] == "sgcc_distribution_technical_v1"


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

    mappings_by_key = {
        (chapter["volume_type"], chapter["chapter_code"]): {mapping["requirement_id"] for mapping in chapter["requirement_mappings"]}
        for chapter in outline["chapters"]
    }
    all_mapped_ids = set().union(*mappings_by_key.values())

    assert veto["id"] in mappings_by_key[("technical", "1")]
    assert scoring["id"] in mappings_by_key[("technical", "12")]
    assert special["id"] in mappings_by_key[("technical", "15")]
    assert hard["id"] in mappings_by_key[("technical", "1")]
    assert ignored["id"] not in all_mapped_ids
    assert outline["metadata_json"]["unmapped_hard_requirement_ids"] == []


def test_chapter_outline_lists_input_requirements() -> None:
    requirement = _requirement(
        "project_team",
        title="项目经理须提供证书",
        source_metadata={"constraint_subtype": "personnel_certificate"},
    )

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[requirement])
    chapter = next(item for item in outline["chapters"] if item["volume_type"] == "technical" and item["chapter_code"] == "6")

    assert "项目经理须提供证书" in chapter["outline_md"]
    assert "招标文件 AI 解析结果为最高优先级" in chapter["outline_md"]


def test_non_legacy_outline_does_not_map_by_raw_category_fallback() -> None:
    requirement = _requirement(
        "technical",
        title="泛化技术要求",
        source_metadata={},
    )

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[requirement])
    all_mappings = [
        mapping
        for chapter in outline["chapters"]
        for mapping in chapter["requirement_mappings"]
        if mapping["requirement_id"] == requirement["id"]
    ]

    assert all_mappings == []
    assert str(requirement["id"]) not in outline["metadata_json"]["unmapped_hard_requirement_ids"]


def test_no_conflict_outline_preserves_template_structure_byte_for_byte() -> None:
    outline = plan_bid_outline_from_requirements(
        project_id=uuid4(),
        requirements=[
            _requirement("technical", source_metadata={"constraint_subtype": "quality_target"}),
            _requirement("technical", source_metadata={"constraint_subtype": "safety_civilized"}),
        ],
    )

    expected = [
        (chapter["volume_type"], chapter["chapter_code"], chapter["chapter_title"], chapter.get("parent_code"))
        for chapter in base_bid_chapters()
    ]
    actual = [
        (chapter["volume_type"], chapter["chapter_code"], chapter["chapter_title"], chapter.get("parent_code"))
        for chapter in outline["chapters"]
    ]
    assert actual == expected


def test_construction_method_maps_to_organization_and_technical_measure_chapters() -> None:
    requirement = _requirement(
        "technical",
        title="施工技术措施",
        source_metadata={"constraint_subtype": "construction_method"},
    )

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[requirement])
    mapped_codes = {
        chapter["chapter_code"]
        for chapter in outline["chapters"]
        if any(mapping["requirement_id"] == requirement["id"] for mapping in chapter["requirement_mappings"])
    }

    assert {"8", "8.3", "8.4"} <= mapped_codes


def test_sgcc_standard_maps_to_construction_and_spec_response_chapters() -> None:
    requirement = _requirement(
        "technical",
        title="国网标准符合性",
        source_metadata={"constraint_subtype": "sgcc_standard_compliance"},
    )

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[requirement])
    mapped_codes = {
        chapter["chapter_code"]
        for chapter in outline["chapters"]
        if any(mapping["requirement_id"] == requirement["id"] for mapping in chapter["requirement_mappings"])
    }

    assert {"8", "8.1", "8.4", "8.15", "13"} <= mapped_codes


def test_chapter_8_internal_subsections_receive_topic_constraints() -> None:
    requirements = [
        _requirement("technical", title="人员组织", source_metadata={"constraint_subtype": "personnel_count"}),
        _requirement("technical", title="质量目标", source_metadata={"constraint_subtype": "quality_target"}),
        _requirement("schedule", title="计划工期", source_metadata={"constraint_subtype": "schedule_target"}),
        _requirement("technical", title="安全文明施工", source_metadata={"constraint_subtype": "safety_civilized"}),
    ]

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=requirements)
    mapped_by_title = {
        requirement["title"]: {
            chapter["chapter_code"]
            for chapter in outline["chapters"]
            if any(mapping["requirement_id"] == requirement["id"] for mapping in chapter["requirement_mappings"])
        }
        for requirement in requirements
    }

    assert {"6", "8.14"} <= mapped_by_title["人员组织"]
    assert {"8.5", "10.1"} <= mapped_by_title["质量目标"]
    assert {"3", "8.7", "10.3"} <= mapped_by_title["计划工期"]
    assert {"8.6", "10.2"} <= mapped_by_title["安全文明施工"]


def test_technical_scoring_maps_to_supporting_materials_and_relevant_chapter() -> None:
    requirement = _requirement(
        "scoring",
        title="质量评分点",
        requirement_text="质量保证措施完整得满分。",
        source_metadata={"constraint_subtype": "technical_scoring_response", "chapter_hint": "10.1"},
    )

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[requirement])
    mapped_codes = {
        chapter["chapter_code"]
        for chapter in outline["chapters"]
        if any(mapping["requirement_id"] == requirement["id"] for mapping in chapter["requirement_mappings"])
    }

    assert {"12", "10.1"} <= mapped_codes


def test_veto_rejection_maps_to_existing_deviation_and_response_chapters() -> None:
    requirement = _requirement(
        "veto",
        title="否决项",
        requirement_text="投标文件存在重大偏差将被否决。",
        source_metadata={"constraint_subtype": "veto_rejection"},
    )

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[requirement])
    mapped_keys = {
        (chapter["volume_type"], chapter["chapter_code"])
        for chapter in outline["chapters"]
        if any(mapping["requirement_id"] == requirement["id"] for mapping in chapter["requirement_mappings"])
    }

    assert {("business", "1"), ("technical", "1")} <= mapped_keys


def test_constraint_subtype_column_drives_confirmed_constraint_mapping() -> None:
    project_id = uuid4()
    requirement_id = uuid4()
    constraint_id = uuid4()

    outline = plan_bid_outline_from_confirmed_constraints(
        project_id=project_id,
        constraint_set={
            "id": uuid4(),
            "version": 2,
            "status": "confirmed",
            "items": [
                {
                    "id": constraint_id,
                    "requirement_id": requirement_id,
                    "category": "technical",
                    "constraint_subtype": "safety_civilized",
                    "status": "accepted",
                    "title": "安全文明施工",
                    "constraint_text": "须落实安全文明施工措施。",
                    "metadata_json": {},
                }
            ],
        },
    )

    chapter = next(item for item in outline["chapters"] if item["volume_type"] == "technical" and item["chapter_code"] == "10.2")

    assert chapter["requirement_ids"] == [requirement_id]


def test_sgcc_distribution_business_outline_preserves_parent_codes() -> None:
    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[])

    chapter = next(item for item in outline["chapters"] if item["chapter_code"] == "8.1.1")

    assert chapter["chapter_title"] == "资产负债表2023"
    assert chapter["parent_code"] == "8.1"
    assert chapter["metadata_json"]["template_key"] == "sgcc_distribution_business_v1"
    assert chapter["metadata_json"]["source_sample"] == "docs/samples/国网公司配网工程商务标目录.md"


def test_sgcc_distribution_technical_outline_uses_sample_numbering() -> None:
    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[])

    chapter = next(item for item in outline["chapters"] if item["volume_type"] == "technical" and item["chapter_code"] == "8.15")

    assert chapter["chapter_title"] == "国网年度框架施工工程投标其他创新内容"
    assert chapter["parent_code"] == "8"
    assert chapter["metadata_json"]["template_key"] == "sgcc_distribution_technical_v1"
    assert chapter["metadata_json"]["source_sample"] == "docs/samples/国网公司配网工程技术标目录.md"


def test_plan_bid_outline_from_confirmed_constraints_uses_constraint_items() -> None:
    project_id = uuid4()
    requirement_id = uuid4()
    constraint_id = uuid4()
    outline = plan_bid_outline_from_confirmed_constraints(
        project_id=project_id,
        constraint_set={
            "id": uuid4(),
            "version": 2,
            "status": "confirmed",
            "items": [
                {
                    "id": constraint_id,
                    "requirement_id": requirement_id,
                    "category": "technical",
                    "status": "accepted",
                    "title": "质量目标",
                    "constraint_text": "质量目标：工程质量合格率100%。",
                    "source_locator": "p10",
                    "metadata_json": {"constraint_subtype": "quality_target"},
                }
            ],
        },
    )

    chapter = next(item for item in outline["chapters"] if item["volume_type"] == "technical" and item["chapter_code"] == "10.1")

    assert chapter["requirement_ids"] == [requirement_id]
    assert chapter["requirement_mappings"][0]["source_constraint_id"] == str(constraint_id)
    assert outline["metadata_json"]["source_constraint_set_version"] == 2
    assert outline["metadata_json"]["source_requirement_count"] == 1


def test_build_bid_outline_prefers_latest_confirmed_constraint_set(monkeypatch) -> None:
    project_id = uuid4()
    requirement_id = uuid4()
    constraint_id = uuid4()
    persisted = {}

    class _RequirementRepo:
        def list_by_project(self, conn, *, project_id):
            raise AssertionError("raw requirements should not be loaded when a confirmed constraint set exists")

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {
                "id": uuid4(),
                "version": 4,
                "status": "confirmed",
                "items": [
                    {
                        "id": constraint_id,
                        "requirement_id": requirement_id,
                        "category": "technical",
                        "status": "accepted",
                        "title": "质量目标",
                        "constraint_text": "质量目标：工程质量合格率100%。",
                        "metadata_json": {"constraint_subtype": "quality_target"},
                    }
                ],
            }

    class _OutlineRepo:
        def replace_for_project(self, conn, *, project_id, outline):
            persisted["outline"] = outline
            return outline

    monkeypatch.setattr("tender_backend.services.bid_outline_planner.RequirementRepository", _RequirementRepo)
    monkeypatch.setattr("tender_backend.services.bid_outline_planner.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.bid_outline_planner.BidOutlineRepository", _OutlineRepo)

    outline = build_bid_outline(object(), project_id=project_id)

    assert outline is persisted["outline"]
    assert outline["metadata_json"]["constraint_source_of_truth"] == "confirmed_constraint_set"
