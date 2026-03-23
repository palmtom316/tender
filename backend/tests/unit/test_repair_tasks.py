from __future__ import annotations

from uuid import uuid4

from tender_backend.services.norm_service.repair_tasks import build_repair_tasks
from tender_backend.services.norm_service.validation import ValidationIssue, validate_clauses


def _clause(**overrides: object) -> dict:
    clause = {
        "id": uuid4(),
        "clause_no": "1.0.1",
        "node_type": "clause",
        "clause_text": "条文正文",
        "page_start": 3,
        "page_end": 3,
        "clause_type": "normative",
        "source_type": "text",
        "source_ref": "document_section:s1",
        "source_refs": ["document_section:s1"],
    }
    clause.update(overrides)
    return clause


def test_build_repair_tasks_promotes_all_tables_to_candidates() -> None:
    tasks = build_repair_tasks([
        _clause(
            source_type="table",
            source_ref="table:t1",
            source_refs=["table:t1"],
            page_start=8,
            page_end=9,
            clause_text="表 3.2.1 主要参数",
        )
    ], issues=[])

    assert len(tasks) == 1
    assert tasks[0].task_type == "table_repair"
    assert tasks[0].source_ref == "table:t1"
    assert tasks[0].trigger_reasons == ["table.high_recall"]


def test_build_repair_tasks_deduplicates_symbol_numeric_issues_by_source_ref() -> None:
    issues = [
        ValidationIssue(
            code="numeric.double_dot",
            severity="warning",
            message="数字异常",
            source_ref="document_section:s1",
            page_start=12,
            page_end=12,
            snippet="10..5kV",
        ),
        ValidationIssue(
            code="unit.incomplete_token",
            severity="warning",
            message="单位异常",
            source_ref="document_section:s1",
            page_start=12,
            page_end=12,
            snippet="30 MP",
        ),
    ]

    tasks = build_repair_tasks([], issues=issues)

    assert len(tasks) == 1
    assert tasks[0].task_type == "symbol_numeric_repair"
    assert tasks[0].source_ref == "document_section:s1"
    assert tasks[0].trigger_reasons == ["numeric.double_dot", "unit.incomplete_token"]


def test_validate_clauses_emits_repairable_source_metadata() -> None:
    result = validate_clauses([
        _clause(
            clause_text="抗压强度不应小于30 MP",
            page_start=15,
            page_end=16,
            source_ref="document_section:s15",
            source_refs=["document_section:s15"],
        )
    ])

    issue = next(item for item in result.issues if item.code == "unit.incomplete_token")

    assert issue.source_ref == "document_section:s15"
    assert issue.page_start == 15
    assert issue.page_end == 16
    assert issue.snippet == "抗压强度不应小于30 MP"
