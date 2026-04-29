from __future__ import annotations

from tender_backend.services.template_service.context_preview import (
    _apply_field_mappings,
    _build_render_context_from_bindings,
    _matches_filters,
    _select_records,
    validate_field_mapping_mode,
    validate_field_mappings,
    validate_selection_mode,
    validate_source_type,
)


def test_matches_filters_supports_equals_contains_and_record_ids() -> None:
    record = {
        "id": "abc",
        "company_name": "REDACTED",
        "role_name": "项目总经理",
    }
    assert _matches_filters(record, {"equals": {"role_name": "项目总经理"}}) is True
    assert _matches_filters(record, {"contains": {"company_name": "REDACTED"}}) is True
    assert _matches_filters(record, {"record_ids": ["abc", "def"]}) is True
    assert _matches_filters(record, {"equals": {"role_name": "技术负责人"}}) is False


def test_select_records_handles_all_latest_first_and_by_id() -> None:
    records = [{"id": "1"}, {"id": "2"}]
    assert _select_records(records, "all") == records
    assert _select_records(records, "latest") == {"id": "1"}
    assert _select_records(records, "first") == {"id": "1"}
    assert _select_records(records, "by_id") == {"id": "1"}


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
            "data": {"company_name": "REDACTED"},
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

    assert context["company"]["company_name"] == "REDACTED"
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
        "company_name": "REDACTED",
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

    assert mapped["company_name"] == "REDACTED"
    assert mapped["company_title"] == "REDACTED"
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
