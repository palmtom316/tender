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


def test_build_tree_reattaches_flat_clause_to_nearest_existing_ancestor() -> None:
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
    assert clauses[1]["parent_id"] == clauses[0]["id"]


def test_build_tree_preserves_clause_source_metadata() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "6.1.1",
                "clause_text": "额定电压不应低于 10kV。",
                "source_type": "table",
                "source_label": "表格: 主要参数",
                "source_ref": "table:t1",
            }
        ],
        standard_id,
    )

    assert len(clauses) == 1
    assert clauses[0]["source_type"] == "table"
    assert clauses[0]["source_label"] == "表格: 主要参数"
    assert clauses[0]["source_ref"] == "table:t1"


def test_build_tree_normalizes_blank_and_string_page_numbers() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "6.1.2",
                "clause_text": "条文内容",
                "page_start": "",
                "page_end": "12",
            }
        ],
        standard_id,
    )

    assert len(clauses) == 1
    assert clauses[0]["page_start"] is None
    assert clauses[0]["page_end"] == 12


def test_build_tree_deduplicates_nested_siblings_with_same_projected_node_key() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.3.2",
                "clause_text": "主条文",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "第1项正文（首次）",
                    },
                    {
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "第1项正文（重复）",
                    },
                ],
            }
        ],
        standard_id,
    )

    assert len(clauses) == 2
    assert clauses[0]["node_key"] == "4.3.2"
    assert clauses[1]["node_key"] == "4.3.2#1"
    assert clauses[1]["clause_text"] == "第1项正文（首次）"


def test_build_tree_infers_parent_for_flat_entries_even_when_mixed_with_nested_entries() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "5.1",
                "clause_title": "一般规定",
                "clause_text": "",
            },
            {
                "clause_no": "5.1.1",
                "clause_text": "互感器在运输、保管期间应防止受潮。",
            },
            {
                "clause_no": "5.1.3",
                "clause_text": "互感器到达现场后安装前的保管，应作下列外观检查：",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "互感器外观应完整。",
                    }
                ],
            },
        ],
        standard_id,
    )

    clause_5_1 = next(clause for clause in clauses if clause["node_key"] == "5.1")
    clause_5_1_1 = next(clause for clause in clauses if clause["node_key"] == "5.1.1")
    clause_5_1_3 = next(clause for clause in clauses if clause["node_key"] == "5.1.3")

    assert clause_5_1["parent_id"] is None
    assert clause_5_1_1["parent_id"] == clause_5_1["id"]
    assert clause_5_1_3["parent_id"] == clause_5_1["id"]


def test_build_tree_deduplicates_flat_and_nested_clause_entries_with_same_clause_no() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.10",
                "clause_title": "热油循环",
                "clause_text": "",
                "children": [
                    {
                        "clause_no": "4.10.1",
                        "clause_text": "330kV及以上变压器、电抗器真空注油后应进行热油循环。",
                        "children": [
                            {
                                "node_type": "item",
                                "node_label": "1",
                                "clause_text": "热油循环前，应对油管抽真空。",
                            }
                        ],
                    }
                ],
            },
            {
                "clause_no": "4.10.1",
                "clause_text": "330kV及以上变压器、电抗器真空注油后应进行热油循环。",
            },
        ],
        standard_id,
    )

    clause_4_10 = next(clause for clause in clauses if clause["node_key"] == "4.10")
    clause_4_10_1 = [clause for clause in clauses if clause["clause_no"] == "4.10.1" and clause["node_type"] == "clause"]
    item = next(clause for clause in clauses if clause["node_type"] == "item")

    assert len(clause_4_10_1) == 1
    assert clause_4_10_1[0]["node_key"] == "4.10.1"
    assert clause_4_10_1[0]["parent_id"] == clause_4_10["id"]
    assert item["parent_id"] == clause_4_10_1[0]["id"]


def test_build_tree_reattaches_clause_to_nearest_existing_ancestor_when_intermediate_outline_missing() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "5",
                "clause_text": "互感器",
            },
            {
                "clause_no": "5.3.6",
                "clause_text": "互感器的下列各部位应可靠接地：",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "互感器的外壳。",
                    }
                ],
            },
        ],
        standard_id,
    )

    clause_5 = next(clause for clause in clauses if clause["node_key"] == "5")
    clause_5_3_6 = next(clause for clause in clauses if clause["node_key"] == "5.3.6")
    item = next(clause for clause in clauses if clause["node_key"] == "5.3.6#1")

    assert clause_5["parent_id"] is None
    assert clause_5_3_6["parent_id"] == clause_5["id"]
    assert item["parent_id"] == clause_5_3_6["id"]
