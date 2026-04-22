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


def test_build_tree_reclassifies_parenthesized_flat_entries_as_items_under_previous_clause() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "8.0.13",
                "clause_text": "局部放电测量应符合下列规定：",
            },
            {
                "clause_no": "（3）",
                "clause_text": "在施加试验电压的整个期间，应监测局部放电量。",
            },
            {
                "clause_no": "(4)",
                "clause_text": "在施加试验电压的前后，应测量所有测量通道上的背景噪声水平。",
            },
        ],
        standard_id,
    )

    clause = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "8.0.13")
    items = [item for item in clauses if item["node_type"] == "item"]

    assert [item["node_label"] for item in items] == ["(3)", "(4)"]
    assert all(item["clause_no"] == "8.0.13" for item in items)
    assert all(item["parent_id"] == clause["id"] for item in items)
    assert not any(item["clause_no"] in {"（3）", "(4)"} and item["node_type"] == "clause" for item in clauses)


def test_build_tree_reclassifies_unnumbered_flat_entries_as_items_when_parent_invites_list() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.1.2",
                "clause_text": "变压器或电抗器的装卸应符合下列规定：",
            },
            {
                "clause_no": None,
                "clause_text": "断路器零部件应齐全、清洁、完好。",
            },
            {
                "clause_no": None,
                "clause_text": "灭弧室或罐体和绝缘支柱内预充的六氟化硫等气体的压力值应符合产品技术文件要求。",
            },
        ],
        standard_id,
    )

    clause = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "4.1.2")
    items = [item for item in clauses if item["node_type"] == "item"]

    assert [item["node_label"] for item in items] == ["1", "2"]
    assert all(item["clause_no"] == "4.1.2" for item in items)
    assert all(item["parent_id"] == clause["id"] for item in items)
    assert not any(item["clause_no"] is None and item["node_type"] == "clause" for item in clauses)


def test_build_tree_keeps_table_entries_without_clause_no_out_of_previous_clause_items() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.1.2",
                "clause_text": "变压器或电抗器的装卸应符合下列规定：",
            },
            {
                "clause_no": None,
                "clause_title": "表4.1.2主要参数",
                "clause_text": "额定电压：10kV。",
                "source_type": "table",
            },
        ],
        standard_id,
    )

    host_clause = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "4.1.2")
    table_clause = next(
        item
        for item in clauses
        if item["source_type"] == "table" and item["clause_title"] == "表4.1.2主要参数"
    )

    assert table_clause["node_type"] == "clause"
    assert table_clause["clause_no"] is None
    assert table_clause["parent_id"] is None
    assert table_clause["id"] != host_clause["id"]


def test_build_tree_keeps_auto_inferred_items_for_different_parents_with_same_labels() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.1.2",
                "clause_text": "变压器或电抗器的装卸应符合下列规定：",
            },
            {
                "clause_no": None,
                "clause_text": "断路器零部件应齐全、清洁、完好。",
            },
            {
                "clause_no": "4.1.3",
                "clause_text": "设备检查应符合下列规定：",
            },
            {
                "clause_no": None,
                "clause_text": "各元件的紧固螺栓应齐全、无松动。",
            },
        ],
        standard_id,
    )

    items = [item for item in clauses if item["node_type"] == "item"]

    assert len(items) == 2
    assert {(item["clause_no"], item["node_label"]) for item in items} == {
        ("4.1.2", "1"),
        ("4.1.3", "1"),
    }


def test_build_tree_attaches_explicit_item_nodes_without_clause_no_to_previous_clause() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.1.2",
                "clause_text": "变压器或电抗器的装卸应符合下列规定：",
            },
            {
                "node_type": "item",
                "node_label": "1",
                "clause_text": "断路器零部件应齐全、清洁、完好。",
            },
            {
                "clause_no": "4.1.3",
                "clause_text": "设备检查应符合下列规定：",
            },
            {
                "node_type": "item",
                "node_label": "1",
                "clause_text": "各元件的紧固螺栓应齐全、无松动。",
            },
        ],
        standard_id,
    )

    items = [item for item in clauses if item["node_type"] == "item"]

    assert len(items) == 2
    assert {(item["clause_no"], item["node_label"]) for item in items} == {
        ("4.1.2", "1"),
        ("4.1.3", "1"),
    }


def test_build_tree_attaches_explicit_item_without_clause_no_to_latest_clause_even_without_list_hint() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "5.2.1",
                "clause_text": "GIS中的避雷器、电压互感器单元与主回路的连接程序应考虑设备交流耐压试验的影响。",
            },
            {
                "node_type": "item",
                "node_label": "8",
                "clause_text": "GIS中的避雷器、电压互感器单元与主回路的连接程序应考虑设备交流耐压试验的影响。",
            },
        ],
        standard_id,
    )

    clause = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "5.2.1")
    item = next(item for item in clauses if item["node_type"] == "item")

    assert item["clause_no"] == "5.2.1"
    assert item["parent_id"] == clause["id"]


def test_build_tree_reclassifies_nested_leading_numeric_children_as_items() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "8.0.13",
                "clause_text": "绕组连同套管的交流耐压试验，应符合下列规定：",
                "children": [
                    {
                        "clause_text": "2)外施交流电压试验电压的频率不应低于40Hz。",
                    },
                    {
                        "clause_text": "3)感应电压试验时，试验电压的频率应大于额定频率。",
                    },
                ],
            }
        ],
        standard_id,
    )

    host_clause = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "8.0.13")
    items = [item for item in clauses if item["node_type"] == "item"]

    assert [item["node_label"] for item in items] == ["2)", "3)"]
    assert all(item["clause_no"] == "8.0.13" for item in items)
    assert all(item["parent_id"] == host_clause["id"] for item in items)
    assert len([item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "8.0.13"]) == 1


def test_build_tree_reclassifies_nested_same_clause_number_sequence_children() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "8.0.13",
                "clause_text": "绕组连同套管的交流耐压试验，应符合下列规定：",
                "children": [
                    {
                        "clause_no": "8.0.13",
                        "clause_text": "2)外施交流电压试验电压的频率不应低于40Hz。",
                    },
                    {
                        "clause_no": "8.0.13",
                        "clause_text": "3)感应电压试验时，试验电压的频率应大于额定频率。",
                    },
                ],
            }
        ],
        standard_id,
    )

    host_clause = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "8.0.13")
    items = [item for item in clauses if item["node_type"] == "item"]

    assert [item["node_label"] for item in items] == ["2)", "3)"]
    assert all(item["clause_no"] == "8.0.13" for item in items)
    assert all(item["parent_id"] == host_clause["id"] for item in items)
    assert len([item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "8.0.13"]) == 1


def test_build_tree_repairs_top_level_orphan_items_even_when_other_entries_have_children() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "4.1.2",
                "clause_text": "变压器或电抗器的装卸应符合下列规定：",
                "children": [
                    {
                        "node_type": "item",
                        "node_label": "1",
                        "clause_text": "吊装器具应符合产品技术文件要求。",
                    }
                ],
            },
            {
                "node_type": "item",
                "node_label": "2",
                "clause_text": "断路器零部件应齐全、清洁、完好。",
            },
        ],
        standard_id,
    )

    clause = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "4.1.2")
    orphan = next(item for item in clauses if item["node_type"] == "item" and item["node_label"] == "2")

    assert orphan["clause_no"] == "4.1.2"
    assert orphan["parent_id"] == clause["id"]


def test_build_tree_promotes_clause_like_item_labels_into_child_clauses() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "13",
                "clause_title": "六氟化硫封闭式组合电器",
                "clause_text": "",
            },
            {
                "node_type": "item",
                "node_label": "13.0.4",
                "clause_text": "密封性试验，应符合下列规定：",
            },
            {
                "node_type": "item",
                "node_label": "13.0.5",
                "clause_text": "测量六氟化硫气体含水量，应符合下列规定：",
            },
        ],
        standard_id,
    )

    chapter = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "13")
    promoted = [item for item in clauses if item["clause_no"] in {"13.0.4", "13.0.5"}]

    assert len(promoted) == 2
    assert all(item["node_type"] == "clause" for item in promoted)
    assert all(item["parent_id"] == chapter["id"] for item in promoted)
    assert not any(item["node_type"] == "item" and item["node_label"] in {"13.0.4", "13.0.5"} for item in clauses)


def test_build_tree_demotes_nested_children_of_parenthesized_items_to_subitems() -> None:
    standard_id = uuid4()

    clauses = build_tree(
        [
            {
                "clause_no": "8.0.14",
                "clause_text": "绕组连同套管的长时感应电压试验带局部放电测量（ACLD），应符合下列规定：",
                "children": [
                    {
                        "clause_no": "（3）",
                        "clause_text": "施加电压方法应符合下列规定：",
                        "children": [
                            {
                                "node_type": "item",
                                "node_label": "1)",
                                "clause_text": "应在不大于 U2 / 3 的电压下接通电源；",
                            },
                            {
                                "node_type": "item",
                                "node_label": "2)",
                                "clause_text": "电压上升到 U2，应保持 5min；",
                            },
                        ],
                    },
                    {
                        "clause_no": "(4)",
                        "clause_text": "局部放电测量应符合下列规定：",
                        "children": [
                            {
                                "node_type": "item",
                                "node_label": "1)",
                                "clause_text": "在施加试验电压的整个期间，应监测局部放电量；",
                            }
                        ],
                    },
                ],
            }
        ],
        standard_id,
    )

    clause = next(item for item in clauses if item["node_type"] == "clause" and item["clause_no"] == "8.0.14")
    parent_items = {
        item["node_label"]: item
        for item in clauses
        if item["node_type"] == "item" and item["parent_id"] == clause["id"]
    }
    subitems = [item for item in clauses if item["node_type"] == "subitem"]

    assert set(parent_items) == {"(3)", "(4)"}
    assert {(item["parent_id"], item["node_label"]) for item in subitems} == {
        (parent_items["(3)"]["id"], "1)"),
        (parent_items["(3)"]["id"], "2)"),
        (parent_items["(4)"]["id"], "1)"),
    }
    assert not any(
        item["node_type"] == "item" and item["parent_id"] == clause["id"] and item["node_label"] in {"1)", "2)"}
        for item in clauses
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
