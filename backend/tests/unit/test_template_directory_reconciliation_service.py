from __future__ import annotations

from uuid import uuid4

from tender_backend.services.template_directory_reconciliation_service import TemplateDirectoryReconciliationService


def _chapter(code: str, title: str, *, parent_id=None, chapter_id=None, source_id=None):
    return type(
        "Chapter",
        (),
        {
            "id": chapter_id or uuid4(),
            "parent_id": parent_id,
            "source_template_item_id": source_id or uuid4(),
            "chapter_code": code,
            "chapter_title": title,
            "enabled": True,
            "sort_order": int(code.split(".")[-1]) if code.split(".")[-1].isdigit() else 0,
            "metadata_json": {},
        },
    )()


def _requirement(code: str, title: str, **extra):
    return {"id": uuid4(), "directory_code": code, "title": title, "category": "directory", **extra}


def _types(suggestions):
    return [item.suggestion_type for item in suggestions]


def test_directory_diff_suggests_add_disable_rename_reorder_split_and_merge() -> None:
    service = TemplateDirectoryReconciliationService()
    chapters = [_chapter("1", "资格证明"), _chapter("2", "旧章节"), _chapter("3", "施工方案"), _chapter("4", "安全措施"), _chapter("5", "质量措施")]
    requirements = [
        _requirement("1", "资格证明文件"),
        _requirement("3", "安全措施"),
        _requirement("4", "施工方案"),
        _requirement("6", "进度计划"),
        _requirement("7.1", "质量保证体系"),
        _requirement("7.2", "质量控制措施"),
        _requirement("8", "安全与文明施工"),
    ]

    suggestions = service.build_suggestions(requirements, chapters)
    by_type = _types(suggestions)

    assert "add_chapter" in by_type
    assert "disable_chapter" in by_type
    assert "rename_chapter" in by_type
    assert "reorder_chapter" in by_type
    assert "split_chapter" in by_type
    assert "merge_chapter" in by_type


def test_three_level_directory_is_not_flattened_and_cross_level_move_preserves_identity() -> None:
    service = TemplateDirectoryReconciliationService()
    stable_source = uuid4()
    parent = uuid4()
    chapters = [_chapter("2.1", "施工方法", parent_id=parent, source_id=stable_source)]
    requirements = [_requirement("1.3.1", "施工方法", source_template_item_id=stable_source)]

    suggestions = service.build_suggestions(requirements, chapters)

    move = next(item for item in suggestions if item.suggestion_type == "move_chapter")
    assert move.payload["required_parent_code"] == "1.3"
    assert move.payload["required_code"] == "1.3.1"
    assert not any(item.suggestion_type == "add_chapter" and item.required_code == "1.3.1" for item in suggestions)


def test_clarification_changes_are_critical_and_non_skippable_without_reason() -> None:
    service = TemplateDirectoryReconciliationService()
    chapters = [_chapter("9", "签字盖章")]
    requirements = [
        _requirement(
            "9",
            "签字盖章及骑缝章",
            source_type="tender_addendum",
            clarification_id=uuid4(),
            mandatory=True,
            requirement_text="补遗要求增加骑缝章，必须响应。",
        )
    ]

    suggestions = service.build_suggestions(requirements, chapters)

    suggestion = next(item for item in suggestions if item.suggestion_type in {"rename_chapter", "add_chapter"})
    assert suggestion.source_type == "tender_addendum"
    assert suggestion.severity == "critical"
    assert suggestion.skippable is False


def test_apply_rejects_skipping_critical_addendum_without_not_applicable_reason() -> None:
    service = TemplateDirectoryReconciliationService()
    suggestion = service.build_suggestions(
        [_requirement("1", "盖章", source_type="tender_addendum", mandatory=True)],
        [],
    )[0]

    try:
        service.validate_apply_selection([suggestion], skipped_suggestion_ids=[suggestion.id], not_applicable_reasons={})
    except ValueError as exc:
        assert "not_applicable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("critical addendum skip must require explicit not_applicable reason")
