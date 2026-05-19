from __future__ import annotations

from tender_backend.services.template_service.context_preview import (
    _apply_field_mappings,
    _build_render_context_from_bindings,
    _matches_filters,
    _select_records,
    _suggest_field_mapping_group,
    suggest_field_mappings,
    validate_field_mapping_mode,
    validate_field_mappings,
    validate_selection_mode,
    validate_source_type,
)


def test_matches_filters_supports_equals_contains_and_record_ids() -> None:
    record = {
        "id": "abc",
        "company_name": "重庆示例电力工程有限责任公司",
        "role_name": "项目总经理",
    }
    assert _matches_filters(record, {"equals": {"role_name": "项目总经理"}}) is True
    assert _matches_filters(record, {"contains": {"company_name": "示例电力"}}) is True
    assert _matches_filters(record, {"record_ids": ["abc", "def"]}) is True
    assert _matches_filters(record, {"equals": {"role_name": "技术负责人"}}) is False


def test_select_records_handles_all_latest_first_and_by_id() -> None:
    records = [
        {"id": "1", "created_at": "2024-01-01T00:00:00"},
        {"id": "2", "created_at": "2024-02-01T00:00:00"},
    ]
    assert _select_records(records, "all") == records
    assert _select_records(records, "latest", source_type="company_profile") == {"id": "2", "created_at": "2024-02-01T00:00:00"}
    assert _select_records(records, "first") == {"id": "1", "created_at": "2024-01-01T00:00:00"}
    assert _select_records(records, "by_id", filters={"record_ids": ["2", "1"]}) == {
        "id": "2",
        "created_at": "2024-02-01T00:00:00",
    }


def test_select_records_latest_uses_source_specific_sort_keys() -> None:
    performances = [
        {"id": "p1", "ended_on": "2024-03-01", "started_on": "2023-01-01"},
        {"id": "p2", "ended_on": "2024-06-01", "started_on": "2022-01-01"},
    ]
    certificates = [
        {"id": "c1", "valid_to": "2025-12-31", "valid_from": "2023-01-01"},
        {"id": "c2", "valid_to": "2027-12-31", "valid_from": "2024-01-01"},
    ]
    financials = [
        {"id": "f1", "fiscal_year": 2022, "updated_at": "2024-01-01T00:00:00"},
        {"id": "f2", "fiscal_year": 2024, "updated_at": "2023-01-01T00:00:00"},
    ]
    evidence_assets = [
        {"id": "e1", "issued_on": "2024-01-01", "sort_order": 10},
        {"id": "e2", "issued_on": "2024-05-01", "sort_order": 1},
    ]

    assert _select_records(performances, "latest", source_type="project_performance") == performances[1]
    assert _select_records(certificates, "latest", source_type="qualification_certificate") == certificates[1]
    assert _select_records(financials, "latest", source_type="financial_statement") == financials[1]
    assert _select_records(evidence_assets, "latest", source_type="evidence_asset") == evidence_assets[1]


def test_select_records_by_id_requires_record_ids() -> None:
    try:
        _select_records([{"id": "1"}], "by_id", filters={})
    except ValueError as exc:
        assert "record_ids" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_selection_and_source_validation_reject_unknown_values() -> None:
    try:
        validate_source_type("unknown")
    except ValueError as exc:
        assert "Unsupported source_type" in str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert validate_source_type("evidence_asset") == "evidence_asset"


def test_build_render_context_marks_missing_required_bindings() -> None:
    context, missing = _build_render_context_from_bindings([
        {
            "binding_name": "company_basic",
            "output_key": "company",
            "required": True,
            "data": {"company_name": "重庆示例电力工程有限责任公司"},
        },
        {
            "binding_name": "team_people",
            "output_key": "people",
            "required": True,
            "data": [],
        },
        {
            "binding_name": "optional_note",
            "output_key": "note",
            "required": False,
            "data": None,
        },
    ])

    assert context["company"]["company_name"] == "重庆示例电力工程有限责任公司"
    assert context["people"] == []
    assert missing == ["team_people"]

    try:
        validate_selection_mode("random")
    except ValueError as exc:
        assert "Unsupported selection_mode" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_apply_field_mappings_supports_augment_replace_join_and_formatting() -> None:
    record = {
        "company_name": "重庆示例电力工程有限责任公司",
        "contact_name": "王莉莉",
        "contact_phone": "13800000000",
        "started_on": "2024-01-01T00:00:00",
        "contract_amount": 944.39,
    }

    mapped = _apply_field_mappings(
        record,
        [
            {"target_field": "company_title", "source_field": "company_name"},
            {"target_field": "contact_summary", "source_fields": ["contact_name", "contact_phone"], "transform": "join", "join_with": " / "},
            {"target_field": "started_on_text", "source_field": "started_on", "transform": "date", "date_format": "%Y年%m月%d日"},
            {"target_field": "amount_text", "source_field": "contract_amount", "transform": "number", "decimals": 2},
        ],
        mode="augment",
    )

    assert mapped["company_name"] == "重庆示例电力工程有限责任公司"
    assert mapped["company_title"] == "重庆示例电力工程有限责任公司"
    assert mapped["contact_summary"] == "王莉莉 / 13800000000"
    assert mapped["started_on_text"] == "2024年01月01日"
    assert mapped["amount_text"] == "944.39"

    replaced = _apply_field_mappings(
        record,
        [{"target_field": "contact_summary", "source_fields": ["contact_name", "contact_phone"], "transform": "join", "join_with": " / "}],
        mode="replace",
    )
    assert replaced == {"contact_summary": "王莉莉 / 13800000000"}


def test_field_mapping_validation_rejects_unknown_values() -> None:
    assert validate_field_mapping_mode("augment") == "augment"
    validate_field_mappings([{"target_field": "name", "source_field": "company_name"}])

    try:
        validate_field_mapping_mode("merge")
    except ValueError as exc:
        assert "Unsupported field_mapping_mode" in str(exc)
    else:
        raise AssertionError("expected ValueError")

    try:
        validate_field_mappings([{"target_field": "name", "transform": "join"}])
    except ValueError as exc:
        assert "source_fields" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_suggest_field_mappings_returns_item_specific_presets() -> None:
    company = suggest_field_mappings(item_name="基本情况表", item_code="5.1", source_type="company_profile")
    assert any(mapping["target_field"] == "company_title" for mapping in company)

    people = suggest_field_mappings(item_name="人员汇总表及人员简历表", item_code="6.1", source_type="person_profile")
    assert any(mapping["target_field"] == "role_label" for mapping in people)

    performances = suggest_field_mappings(item_name="业绩情况", item_code="5", source_type="project_performance")
    assert any(mapping["target_field"] == "project_title" for mapping in performances)


def test_suggest_field_mapping_group_exposes_confidence() -> None:
    group = _suggest_field_mapping_group(
        item_name="基本情况表",
        item_code="5.1",
        source_type="company_profile",
    )
    assert group["confidence"] > 0.8
    assert group["field_mapping_mode"] == "augment"
