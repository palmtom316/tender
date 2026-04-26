from __future__ import annotations

from uuid import uuid4

from tender_backend.services.norm_service.validation import validate_clauses


def _clause(**overrides: object) -> dict:
    clause = {
        "id": uuid4(),
        "clause_no": "1.0.1",
        "node_type": "clause",
        "clause_text": "条文正文",
        "page_start": 1,
        "page_end": 1,
        "source_type": "text",
        "source_ref": "document_section:s1",
        "source_refs": ["document_section:s1"],
    }
    clause.update(overrides)
    return clause


def test_validate_clauses_detects_numbering_and_hierarchy_issues() -> None:
    result = validate_clauses([
        _clause(clause_no="1", clause_text="第一章"),
        _clause(clause_no="1.3", clause_text="缺失 1.2"),
        # Depth-2 parent "1.2" with a single child is still flagged (threshold 2).
        _clause(clause_no="1.2.1", clause_text="缺失父级 1.2"),
    ])

    codes = {issue.code for issue in result.issues}

    assert "numbering.gap" in codes
    assert "numbering.missing_parent" in codes


def test_validate_clauses_accepts_outline_parent_codes_for_hierarchy_checks() -> None:
    result = validate_clauses(
        [_clause(clause_no="4.8.8", clause_text="正文")],
        outline_clause_nos={"4.8"},
    )

    codes = {issue.code for issue in result.issues}

    assert "numbering.missing_parent" not in codes


def test_validate_clauses_accepts_top_level_chapter_as_parent_for_x_zero_y_numbering() -> None:
    result = validate_clauses(
        [_clause(clause_no="1.0.3", clause_text="正文")],
        outline_clause_nos={"1"},
    )

    codes = {issue.code for issue in result.issues}

    assert "numbering.missing_parent" not in codes


def test_validate_clauses_detects_page_anchor_and_table_attachment_issues() -> None:
    result = validate_clauses([
        _clause(page_start=None, page_end=None),
        _clause(page_start=8, page_end=5),
        _clause(
            source_type="table",
            source_ref=None,
            source_refs=[],
            page_start=None,
            page_end=None,
            clause_text="表格约束条款",
        ),
    ])

    codes = {issue.code for issue in result.issues}

    assert "page.missing_anchor" in codes
    assert "page.reversed_range" in codes
    assert "table.missing_source_ref" in codes


def test_validate_clauses_detects_numeric_and_symbol_anomalies() -> None:
    result = validate_clauses([
        _clause(clause_no="1.0.1", clause_text="试验电压不应低于10..5kV，严禁??"),
        _clause(clause_no="1.0.2", clause_text="抗压强度不应小于30 MP"),
        _clause(clause_no="1.0.3", clause_text="参数值含乱码�需要人工复核"),
    ])

    codes = {issue.code for issue in result.issues}

    assert "numeric.double_dot" in codes
    assert "unit.incomplete_token" in codes
    assert "symbol.repeated_punctuation" in codes
    assert "symbol.replacement_character" in codes


def test_validate_clauses_extracts_mandatory_and_similar_phrase_flags() -> None:
    result = validate_clauses([
        _clause(clause_text="施工必须满足条件，应执行流程，不得违规，严禁跨越，禁止带电作业，宜按模板，可复核。"),
    ])

    phrases = {(flag.phrase, flag.category) for flag in result.phrase_flags}

    assert ("必须", "mandatory") in phrases
    assert ("应", "mandatory") in phrases
    assert ("不得", "prohibitive") in phrases
    assert ("严禁", "prohibitive") in phrases
    assert ("禁止", "prohibitive") in phrases
    assert ("宜", "advisory") in phrases
    assert ("可", "permissive") in phrases


def test_validate_clauses_prefers_specific_phrase_categories_without_overlap() -> None:
    result = validate_clauses([
        _clause(
            clause_no="1.0.2",
            clause_text="抗压强度不应小于30MPa，且应符合表3.1.2的规定，见图2.0.1。",
        ),
        _clause(
            clause_no="1.0.2",
            clause_type="commentary",
            clause_text="条文说明：不应小于30MPa 为最低要求。",
        ),
    ])

    phrases = {(flag.clause_no, flag.phrase, flag.category) for flag in result.phrase_flags}

    assert ("1.0.2", "不应小于", "numeric_constraint") in phrases
    assert ("1.0.2", "应符合表", "table_reference") in phrases
    assert ("1.0.2", "见图", "figure_reference") in phrases
    assert ("1.0.2", "应", "mandatory") not in phrases
    assert len(result.phrase_flags) == 3
