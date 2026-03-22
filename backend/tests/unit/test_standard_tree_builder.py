from __future__ import annotations

from uuid import uuid4

from tender_backend.services.norm_service.tree_builder import build_tree


def test_build_tree_flattens_nested_clause_items_and_subitems() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.3.2",
                "clause_title": "主体条款",
                "clause_text": "4.3.2 条正文",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "第1项正文",
                        "children": [
                            {
                                "node_type": "subitem",
                                "node_label": "1)",
                                "clause_text": "第1)子项正文",
                            }
                        ],
                    }
                ],
            }
        ],
        standard_id,
    )

    assert len(clauses) == 3

    clause_node = clauses[0]
    item_node = clauses[1]
    subitem_node = clauses[2]

    assert clause_node["node_type"] == "clause"
    assert clause_node["node_key"] == "4.3.2"
    assert clause_node["node_label"] is None
    assert clause_node["parent_id"] is None

    assert item_node["node_type"] == "item"
    assert item_node["clause_no"] == "4.3.2"
    assert item_node["node_label"] == "1"
    assert item_node["node_key"] == "4.3.2#1"
    assert item_node["parent_id"] == clause_node["id"]

    assert subitem_node["node_type"] == "subitem"
    assert subitem_node["clause_no"] == "4.3.2"
    assert subitem_node["node_label"] == "1)"
    assert subitem_node["node_key"] == "4.3.2#1#1)"
    assert subitem_node["parent_id"] == item_node["id"]


def test_build_tree_keeps_legacy_flat_clause_number_parenting() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "3",
                "clause_title": "总则",
                "clause_text": "",
            },
            {
                "clause_no": "3.2.1",
                "clause_text": "正文",
            },
        ],
        standard_id,
    )

    assert len(clauses) == 2
    assert clauses[0]["node_type"] == "clause"
    assert clauses[0]["node_key"] == "3"
    assert clauses[1]["node_type"] == "clause"
    assert clauses[1]["node_key"] == "3.2.1"
    assert clauses[1]["parent_id"] is None


def test_build_tree_preserves_clause_source_metadata() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "6.1.1",
                "clause_text": "额定电压不应低于 10kV。",
                "source_type": "table",
                "source_label": "表格: 主要参数",
            }
        ],
        standard_id,
    )

    assert len(clauses) == 1
    assert clauses[0]["source_type"] == "table"
    assert clauses[0]["source_label"] == "表格: 主要参数"
