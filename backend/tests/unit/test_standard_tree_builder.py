from __future__ import annotations

from uuid import uuid4

from tender_backend.services.norm_service.tree_builder import build_tree, link_commentary


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


def test_build_tree_keeps_clause_hierarchy_when_entries_mix_nested_items_and_flat_clauses() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.8",
                "clause_title": "本体及附件安装",
                "clause_text": "",
            },
            {
                "clause_no": "4.8.1",
                "clause_text": "220kV及以上变压器本体露空安装附件应符合下列规定：",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "环境相对湿度应小于80%。",
                    }
                ],
            },
            {
                "clause_no": "4.8.2",
                "clause_text": "密封处理应符合下列规定：",
            },
        ],
        standard_id,
    )

    clause_by_no = {
        (clause["clause_no"], clause["node_type"], clause.get("node_label")): clause
        for clause in clauses
    }

    chapter = clause_by_no[("4.8", "clause", None)]
    section_1 = clause_by_no[("4.8.1", "clause", None)]
    section_2 = clause_by_no[("4.8.2", "clause", None)]
    item = clause_by_no[("4.8.1", "item", "1")]

    assert section_1["parent_id"] == chapter["id"]
    assert section_2["parent_id"] == chapter["id"]
    assert item["parent_id"] == section_1["id"]


def test_build_tree_promotes_term_items_that_embed_real_clause_numbers() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "2",
                "clause_title": "术语",
                "clause_text": "2 术语",
                "children": [
                    {
                        "node_type": "item",
                        "clause_text": (
                            "2.0.1 电力变压器 power transformer\n"
                            "具有两个或多个绕组的静止设备。"
                        ),
                    },
                    {
                        "node_type": "item",
                        "clause_text": (
                            "2.0.2 油浸式变压器 oil-immersed type transformer\n"
                            "铁芯和绕组都浸入油中的变压器。"
                        ),
                    },
                ],
            }
        ],
        standard_id,
    )

    chapter = next(clause for clause in clauses if clause["clause_no"] == "2" and clause["node_type"] == "clause")
    term_1 = next(clause for clause in clauses if clause["clause_no"] == "2.0.1")
    term_2 = next(clause for clause in clauses if clause["clause_no"] == "2.0.2")

    assert term_1["node_type"] == "clause"
    assert term_1["parent_id"] == chapter["id"]
    assert term_1["clause_text"].startswith("具有两个或多个绕组")
    assert term_2["node_type"] == "clause"
    assert term_2["parent_id"] == chapter["id"]


def test_build_tree_promotes_numbered_items_when_text_embeds_child_clause_number() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.7",
                "clause_title": "干燥",
                "clause_text": "4.7 干燥",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "1",
                        "clause_no": "4.7",
                        "clause_text": "4.7.1 变压器、电抗器是否需要进行干燥，应综合分析后确定。",
                    },
                    {
                        "node_type": "item",
                        "node_label": "2",
                        "clause_no": "4.7",
                        "clause_text": "4.7.2 设备进行干燥时，宜采用真空热油循环干燥法。",
                    },
                    {
                        "node_type": "item",
                        "node_label": "3",
                        "clause_no": "4.7",
                        "clause_text": "4.7.3 在保持温度不变的情况下，绝缘电阻应保持稳定。",
                    },
                ],
            }
        ],
        standard_id,
    )

    chapter = next(clause for clause in clauses if clause["clause_no"] == "4.7" and clause["node_type"] == "clause")
    child_clause_nos = [
        clause["clause_no"]
        for clause in clauses
        if clause["node_type"] == "clause" and clause["clause_no"] != "4.7"
    ]

    assert child_clause_nos == ["4.7.1", "4.7.2", "4.7.3"]
    assert not any(clause["node_type"] == "item" for clause in clauses[1:])
    assert all(
        clause["parent_id"] == chapter["id"]
        for clause in clauses
        if clause["node_type"] == "clause" and clause["clause_no"] in {"4.7.1", "4.7.2", "4.7.3"}
    )


def test_link_commentary_links_promoted_numbered_child_clauses() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.7",
                "clause_title": "干燥",
                "clause_text": "4.7 干燥",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "2",
                        "clause_no": "4.7",
                        "clause_text": "4.7.2 设备进行干燥时，宜采用真空热油循环干燥法。",
                    }
                ],
            },
            {
                "clause_type": "commentary",
                "clause_no": "4.7.2",
                "clause_text": "本条说明。",
            },
        ],
        standard_id,
    )

    linked = link_commentary(clauses)
    clause_472 = next(clause for clause in linked if clause["clause_type"] == "normative" and clause["clause_no"] == "4.7.2")
    commentary = next(clause for clause in linked if clause["clause_type"] == "commentary")

    assert commentary["commentary_clause_id"] == clause_472["id"]
