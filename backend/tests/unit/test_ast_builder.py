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

    assert len(roots) == 1
    assert roots[0].clause_no == "3"
    assert roots[0].node_key == "3"
    assert roots[0].parent_id is None

    child = roots[0].children[0]
    assert child.clause_no == "3.2.1"
    assert child.node_key == "3.2.1"
    assert child.parent_id == roots[0].id


def test_build_clause_ast_normalizes_untrusted_enum_fields_to_safe_values() -> None:
    standard_id = uuid4()

    roots = build_clause_ast(
        [
            {
                "clause_no": "4.1.2",
                "clause_text": "正文",
                "clause_type": "normative_clause_block_from_ai",
                "source_type": "document_section:s1:derived",
                "node_type": "numbered_list_item_from_model",
            },
        ],
        standard_id,
    )

    assert len(roots) == 1
    assert roots[0].clause_type == "normative"
    assert roots[0].source_type == "text"
    assert roots[0].node_type == "clause"


def test_build_clause_ast_keeps_nested_items_with_same_node_key_from_different_source_labels() -> None:
    standard_id = uuid4()

    roots = build_clause_ast(
        [
            {
                "clause_no": "A.0.1",
                "clause_text": "父条文",
                "children": [
                    {
                        "clause_no": "A.0.1",
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "附录范围内的第1项",
                        "source_label": "附录A",
                    },
                    {
                        "clause_no": "A.0.1",
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "正文引用里的第1项",
                        "source_label": "正文引用",
                    },
                ],
            }
        ],
        standard_id,
    )

    assert len(roots) == 1
    assert [child.source_label for child in roots[0].children] == ["附录A", "正文引用"]
