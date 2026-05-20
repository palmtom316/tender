from __future__ import annotations

import pytest

from tender_backend.services.ad_hoc_chapter_task_card import (
    BLOCKING_STATUSES,
    build_initial_task_card,
    build_task_card_draft_markdown,
    change_task_card_type,
    generate_task_card_outline,
    merge_task_card_metadata,
    missing_required_inputs,
    update_task_card_answers,
    validate_task_card_ready_for_draft,
    validate_task_card_ready_for_outline,
)


def _req(text: str = "应提供施工现场总平面布置及临电临水方案", *, req_id: str = "r1", title: str = "现场总平面布置") -> dict:
    return {
        "id": req_id,
        "title": title,
        "requirement_text": text,
        "source_file": "招标文件.pdf",
        "source_locator": "P32 技术评分标准第4项",
    }


def test_classification_priority_table_over_attachment_and_plan() -> None:
    card = build_initial_task_card(
        chapter_title="承诺函及证明材料清单",
        source_requirements=[_req("须提供承诺函及证明材料清单", title="证明材料清单")],
    )

    assert card["chapter_type"] == "table_checklist"
    assert card["status"] == "needs_input"


def test_classification_green_special_statement_is_attachment() -> None:
    card = build_initial_task_card(
        chapter_title="绿色施工专项说明",
        source_requirements=[_req("须提供绿色施工专项说明材料", title="专项说明")],
    )

    assert card["chapter_type"] == "material_attachment"


def test_classification_green_special_plan_is_technical() -> None:
    card = build_initial_task_card(
        chapter_title="绿色施工专项方案",
        source_requirements=[_req("须提供绿色施工专项方案", title="专项方案")],
    )

    assert card["chapter_type"] == "technical_special_plan"


def test_no_source_requirements_blocks_evidence() -> None:
    card = build_initial_task_card(chapter_title="新增专项方案", source_requirements=[])

    assert card["status"] == "blocked_insufficient_evidence"
    assert card["chapter_type"] == "technical_special_plan"


def test_required_questions_by_type() -> None:
    technical = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[_req()])
    attachment = build_initial_task_card(chapter_title="专项承诺函及相关证明材料", source_requirements=[_req("须提供专项承诺函及证明材料")])
    checklist = build_initial_task_card(chapter_title="人员驻场表", source_requirements=[_req("须提供人员驻场表")])

    assert {item["key"] for item in technical["missing_inputs"]} == {"site_type", "has_site_drawing", "special_constraint"}
    assert {item["key"] for item in attachment["missing_inputs"]} == {"material_source", "attachment_required"}
    assert {item["key"] for item in checklist["missing_inputs"]} == {"table_basis", "manual_review_required"}


def test_validate_ready_for_outline_reports_missing_required_inputs() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[_req()])

    result = validate_task_card_ready_for_outline(card)

    assert result == {"ready": False, "missing_input_keys": ["site_type", "has_site_drawing"]}


def test_patch_rejects_unknown_answer_key() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[_req()])

    with pytest.raises(ValueError, match="unknown answer key"):
        update_task_card_answers(card, answers={"unknown_key": "x"})


def test_patch_rejects_invalid_choice_answer() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[_req()])

    with pytest.raises(ValueError, match="invalid choice"):
        update_task_card_answers(card, answers={"site_type": "火星基地"})


def test_patch_invalidates_outline_when_required_answer_changes() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[_req()])
    card["status"] = "outline_confirmed"
    card["outline"] = [{"heading": "编制依据", "purpose": "说明来源", "must_cover": ["招标要求"]}]

    updated = update_task_card_answers(card, answers={"site_type": "城区道路"})

    assert updated["status"] == "needs_input"
    assert updated["outline"] == []


def test_change_chapter_type_rebuilds_inputs_and_clears_outline_and_coverage() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[_req()])
    card["status"] = "draft_ready"
    card["outline"] = [{"heading": "旧大纲", "purpose": "旧", "must_cover": []}]
    card["coverage_report"] = {"coverage_passed": True}

    updated = change_task_card_type(card, chapter_type="material_attachment")

    assert updated["chapter_type"] == "material_attachment"
    assert updated["status"] == "needs_input"
    assert updated["outline"] == []
    assert updated.get("coverage_report") == {}
    assert {item["key"] for item in updated["missing_inputs"]} == {"material_source", "attachment_required"}


def test_update_answers_after_draft_marks_draft_stale() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[_req()])
    card["status"] = "draft_ready"

    updated = update_task_card_answers(card, answers={"site_type": "城区道路"})

    assert updated["status"] == "needs_input"
    assert updated["draft_stale"] is True


def test_merge_task_card_metadata_preserves_existing_keys() -> None:
    metadata = {
        "template_key": "sgcc_distribution_technical_v1",
        "parent_code": "8",
        "render_mode": "single_docx_section",
        "ad_hoc_required": True,
    }

    merged = merge_task_card_metadata(metadata, {"status": "needs_input", "chapter_type": "technical_special_plan"})

    assert merged["template_key"] == "sgcc_distribution_technical_v1"
    assert merged["parent_code"] == "8"
    assert merged["render_mode"] == "single_docx_section"
    assert merged["ad_hoc_required"] is True
    assert merged["ad_hoc_task_card"]["status"] == "needs_input"


@pytest.mark.parametrize(
    ("chapter_title", "expected_headings"),
    [
        ("临电临水方案", ["编制依据", "工程条件与限制", "专项方案", "安全文明施工", "检查与验收", "招标要求响应表"]),
        ("专项承诺函及相关证明材料", ["材料说明", "资料清单", "附件占位符", "有效性检查"]),
        ("人员驻场表", ["表格说明", "字段定义", "数据来源", "人工确认"]),
    ],
)
def test_generate_task_card_outline_by_type(chapter_title: str, expected_headings: list[str]) -> None:
    card = build_initial_task_card(chapter_title=chapter_title, source_requirements=[_req(chapter_title, title=chapter_title)])
    answers = {item["key"]: item.get("options", ["已确认"])[0] if item["input_type"] == "choice" else "无" for item in card["missing_inputs"] if item.get("required")}
    card = update_task_card_answers(card, answers=answers)

    outline = generate_task_card_outline(card)

    assert [row["heading"] for row in outline] == expected_headings
    assert all("purpose" in row and "must_cover" in row for row in outline)


def test_build_technical_special_plan_draft_and_coverage() -> None:
    card = build_initial_task_card(chapter_title="临时用电方案", source_requirements=[_req("应提供临时用电方案", title="临时用电方案")])
    card = update_task_card_answers(card, answers={"site_type": "城区道路", "has_site_drawing": "uploaded"})
    card["status"] = "outline_confirmed"
    card["outline"] = [
        {"heading": "编制依据", "purpose": "说明来源", "must_cover": ["招标文件P32"]},
        {"heading": "临时用电方案", "purpose": "响应临电要求", "must_cover": ["临时用电方案"]},
        {"heading": "招标要求响应表", "purpose": "逐项响应", "must_cover": ["临时用电方案"]},
    ]

    content, coverage = build_task_card_draft_markdown(card, [_req("应提供临时用电方案", title="临时用电方案")])

    assert "## 编制依据" in content
    assert "## 临时用电方案" in content
    assert "## 招标要求响应表" in content
    assert coverage["coverage_passed"] is True
    assert coverage["covered_requirement_ids"] == ["r1"]


def test_material_attachment_draft_is_short_and_uses_asset_placeholder() -> None:
    card = build_initial_task_card(chapter_title="专项承诺函及相关证明材料", source_requirements=[_req("须提供专项承诺函及证明材料")])
    card = update_task_card_answers(card, answers={"material_source": "user_upload", "attachment_required": "yes"})
    card["status"] = "outline_confirmed"
    card["outline"] = generate_task_card_outline(card)

    content, coverage = build_task_card_draft_markdown(card, [_req("须提供专项承诺函及证明材料")])

    assert "{{ asset:ad_hoc_material_attachment:n }}" in content
    assert "## 资料清单" in content
    assert len(content) < 2000
    assert coverage["coverage_passed"] is True


def test_table_checklist_draft_contains_table_and_placeholders() -> None:
    card = build_initial_task_card(chapter_title="人员驻场表", source_requirements=[_req("须提供人员驻场表", title="人员驻场表")])
    card = update_task_card_answers(card, answers={"table_basis": "user_input", "manual_review_required": "yes"})
    card["status"] = "outline_confirmed"
    card["outline"] = generate_task_card_outline(card)

    content, coverage = build_task_card_draft_markdown(card, [_req("须提供人员驻场表", title="人员驻场表")])

    assert "| 序号 | 字段 | 内容 | 来源 | 确认状态 |" in content
    assert "待确认" in content
    assert coverage["coverage_passed"] is True


def test_validate_task_card_ready_for_draft_requires_confirmed_outline() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[_req()])
    card["status"] = "outline_ready"
    card["outline"] = generate_task_card_outline(update_task_card_answers(card, answers={"site_type": "城区道路", "has_site_drawing": "uploaded"}))

    with pytest.raises(ValueError, match="outline must be confirmed"):
        validate_task_card_ready_for_draft(card)


def test_blocking_statuses_exclude_only_draft_ready() -> None:
    assert "draft_ready" not in BLOCKING_STATUSES
    assert {"task_card_pending", "needs_input", "outline_ready", "outline_confirmed", "blocked_insufficient_evidence"} <= BLOCKING_STATUSES



def test_coverage_report_does_not_cover_unrelated_requirement_from_card_level_must_respond() -> None:
    card = {
        "status": "outline_confirmed",
        "chapter_type": "technical_special_plan",
        "source_anchors": [],
        "must_respond": ["临时用电方案"],
        "missing_inputs": [
            {"key": "site_type", "input_type": "choice", "options": ["城区道路"], "required": True, "answer": "城区道路"},
            {"key": "has_site_drawing", "input_type": "choice", "options": ["uploaded"], "required": True, "answer": "uploaded"},
        ],
        "outline": [
            {"heading": "临时用电方案", "purpose": "响应临电要求", "must_cover": ["临时用电方案"]},
        ],
    }

    _content, coverage = build_task_card_draft_markdown(
        card,
        [
            {"id": "r1", "title": "临时用电方案", "requirement_text": "应提供临时用电方案", "source_locator": "P1"},
            {"id": "r2", "title": "停电组织方案", "requirement_text": "应提供停电组织方案", "source_locator": "P2"},
        ],
    )

    assert coverage["coverage_passed"] is False
    assert coverage["covered_requirement_ids"] == ["r1"]
    assert coverage["missing_requirement_ids"] == ["r2"]


def test_patch_complete_required_answers_moves_to_task_card_pending() -> None:
    card = build_initial_task_card(
        chapter_title="临电临水方案",
        source_requirements=[{"id": "r1", "title": "方案", "requirement_text": "临电临水方案"}],
    )

    updated = update_task_card_answers(
        card,
        answers={"site_type": "城区道路", "has_site_drawing": "uploaded"},
    )

    assert missing_required_inputs(updated) == []
    assert updated["status"] == "task_card_pending"
