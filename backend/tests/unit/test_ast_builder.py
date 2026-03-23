from __future__ import annotations

from uuid import uuid4

from tender_backend.services.norm_service.ast_builder import build_clause_ast


def test_build_clause_ast_preserves_source_refs_and_page_ranges_for_nested_entries() -> None:
    standard_id = uuid4()

    roots = build_clause_ast(
        [
            {
                "clause_no": "4.3.2",
                "clause_text": "主条文",
                "page_start": 15,
                "page_end": 16,
                "source_ref": "document_section:s1",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "1、",
                        "clause_text": "第1项",
                        "page_start": 16,
                        "page_end": 16,
                        "source_refs": ["document_section:s1", "table:t1"],
                    }
                ],
            }
        ],
        standard_id,
    )

    assert len(roots) == 1
    clause = roots[0]
    item = clause.children[0]

    assert clause.clause_no == "4.3.2"
    assert clause.page_start == 15
    assert clause.page_end == 16
    assert clause.source_ref == "document_section:s1"
    assert clause.source_refs == []

    assert item.clause_no == "4.3.2"
    assert item.page_start == 16
    assert item.page_end == 16
    assert item.source_ref is None
    assert item.source_refs == ["document_section:s1", "table:t1"]


def test_build_clause_ast_normalizes_legacy_flat_clause_numbers() -> None:
    standard_id = uuid4()

    roots = build_clause_ast(
        [
            {
                "clause_no": "第3条",
                "clause_text": "总则",
            },
            {
                "clause_no": "3.2.1条",
                "clause_text": "正文",
            },
        ],
        standard_id,
    )

    assert len(roots) == 2
    assert roots[0].clause_no == "3"
    assert roots[0].node_key == "3"
    assert roots[0].parent_id is None

    assert roots[1].clause_no == "3.2.1"
    assert roots[1].node_key == "3.2.1"
    assert roots[1].parent_id is None
