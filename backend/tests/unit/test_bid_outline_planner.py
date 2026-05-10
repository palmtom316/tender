from __future__ import annotations

from uuid import uuid4

from tender_backend.services.bid_outline_planner import (
    build_bid_outline,
    plan_bid_outline_from_confirmed_constraints,
    plan_bid_outline_from_requirements,
)


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
    assert any(chapter["chapter_code"] == "8.1" and chapter["chapter_title"] == "施工组织设计" for chapter in outline["chapters"])
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
    requirement = _requirement("project_team", title="项目经理须提供证书")

    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[requirement])
    chapter = next(item for item in outline["chapters"] if item["chapter_code"] == "1.3")

    assert "项目经理须提供证书" in chapter["outline_md"]
    assert "招标文件 AI 解析结果为最高优先级" in chapter["outline_md"]


def test_sgcc_distribution_business_outline_preserves_parent_codes() -> None:
    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[])

    chapter = next(item for item in outline["chapters"] if item["chapter_code"] == "8.1.1")

    assert chapter["chapter_title"] == "资产负债表2023"
    assert chapter["parent_code"] == "8.1"
    assert chapter["metadata_json"]["template_key"] == "sgcc_distribution_business_v1"
    assert chapter["metadata_json"]["source_sample"] == "docs/samples/国网公司配网工程商务标目录.md"


def test_sgcc_distribution_technical_outline_uses_sample_numbering() -> None:
    outline = plan_bid_outline_from_requirements(project_id=uuid4(), requirements=[])

    chapter = next(item for item in outline["chapters"] if item["volume_type"] == "technical" and item["chapter_code"] == "10.3")

    assert chapter["chapter_title"] == "工程进度计划及保证措施"
    assert chapter["parent_code"] == "10"
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
