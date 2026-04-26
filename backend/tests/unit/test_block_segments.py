from __future__ import annotations

from tender_backend.services.norm_service.block_segments import build_single_standard_blocks


def test_build_single_standard_blocks_classifies_normative_commentary_appendix_and_heading_only() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "4.1.2",
            "title": "变压器或电抗器的装卸",
            "text": "变压器或电抗器的装卸应符合下列规定：",
            "page_start": 6,
            "page_end": 6,
        },
        {
            "id": "s2",
            "section_code": "4.1.2",
            "title": "条文说明",
            "text": "本条说明变压器装卸控制要求。",
            "page_start": 7,
            "page_end": 7,
        },
        {
            "id": "s3",
            "section_code": "A.0.2",
            "title": "附录A 油样性能",
            "text": "附录内容。",
            "page_start": 30,
            "page_end": 30,
        },
        {
            "id": "s4",
            "section_code": "4.2.4",
            "title": "变压器内油样性能",
            "text": "",
            "page_start": 18,
            "page_end": 18,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert [block.segment_type for block in blocks] == [
        "normative_clause_block",
        "commentary_block",
        "appendix_block",
        "heading_only_block",
    ]
    assert blocks[0].clause_no == "4.1.2"
    assert blocks[1].clause_no == "4.1.2"
    assert blocks[2].clause_no == "A.0.2"
    assert blocks[3].section_ids == ["s4"]


def test_build_single_standard_blocks_emits_table_requirement_block_for_named_table() -> None:
    tables = [
        {
            "id": "t1",
            "page_start": 18,
            "page_end": 18,
            "table_title": "表 4.2.4 变压器内油样性能",
            "table_html": "<table><tr><td>含水量</td><td>≤10μL/L</td></tr></table>",
            "raw_json": {"rows": [["含水量", "≤10μL/L"]]},
        }
    ]

    blocks = build_single_standard_blocks([], tables)

    assert len(blocks) == 1
    assert blocks[0].segment_type == "table_requirement_block"
    assert blocks[0].table_title == "表 4.2.4 变压器内油样性能"
    assert blocks[0].page_start == 18
    assert "含水量" in blocks[0].text


def test_build_single_standard_blocks_assigns_confidence_by_block_shape() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "4.1.2",
            "title": "变压器或电抗器的装卸",
            "text": "变压器或电抗器的装卸应符合下列规定：",
            "page_start": 6,
            "page_end": 6,
        },
        {
            "id": "s2",
            "section_code": "4.2.4",
            "title": "变压器内油样性能",
            "text": "",
            "page_start": 18,
            "page_end": 18,
        },
    ]
    tables = [
        {
            "id": "t1",
            "page_start": 18,
            "page_end": 18,
            "table_title": "表 4.2.4 变压器内油样性能",
            "table_html": "<table><tr><td>含水量</td><td>≤10μL/L</td></tr></table>",
        }
    ]

    blocks = build_single_standard_blocks(sections, tables)

    assert [block.confidence for block in blocks] == ["high", "low", "medium"]


def test_build_single_standard_blocks_recovers_clause_no_from_heading_when_section_code_missing() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": None,
            "title": "2.0.1 电力变压器 power transformer",
            "text": "具有两个或多个绕组的静止设备。",
            "page_start": 11,
            "page_end": 11,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert blocks[0].clause_no == "2.0.1"
    assert blocks[0].segment_type == "normative_clause_block"
    assert blocks[0].confidence == "high"


def test_build_single_standard_blocks_recovers_compact_heading_clause_nos_when_section_code_missing() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": None,
            "title": "2术 语",
            "text": "2.0.1架空电力线路 overhead power line",
            "page_start": 11,
            "page_end": 11,
        },
        {
            "id": "s2",
            "section_code": None,
            "title": "6.6岩石基础",
            "text": "16.6.1岩石基础施工时,应逐基逐腿与设计地质资料核对。",
            "page_start": 16,
            "page_end": 16,
        },
        {
            "id": "s3",
            "section_code": None,
            "title": "3.5.3金具的质量应符合国家现行标准的规定。",
            "text": "",
            "page_start": 10,
            "page_end": 10,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert [block.clause_no for block in blocks] == ["2", "6.6", "3.5.3"]
    assert [block.segment_type for block in blocks] == [
        "normative_clause_block",
        "normative_clause_block",
        "normative_clause_block",
    ]


def test_build_single_standard_blocks_does_not_absorb_voltage_prefix_into_compact_clause_no() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": None,
            "title": "8.5.410 kV及以下架设新导线时，弧垂应符合下列规定：",
            "text": "",
            "page_start": 30,
            "page_end": 30,
        },
        {
            "id": "s2",
            "section_code": None,
            "title": "D.0.2010 kV线路杆塔基础检查记录表应按本规范表D.0.20填写。",
            "text": "",
            "page_start": 70,
            "page_end": 70,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert [block.clause_no for block in blocks] == ["8.5.4", "D.0.20"]


def test_build_single_standard_blocks_recovers_split_clause_no_from_chapter_code_and_title_prefix() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "4",
            "title": "2.4设备在保管期间，应经常检查。",
            "text": "其变压器内油样性能应符合表4.2.4的规定：",
            "page_start": 18,
            "page_end": 18,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert blocks[0].clause_no == "4.2.4"
    assert blocks[0].segment_type == "normative_clause_block"


def test_build_single_standard_blocks_does_not_recover_false_clause_no_from_numeric_unit_prefix() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "4",
            "title": "1.131.5MV·A及以上变压器和40MVar及以上的电抗器的装卸及运输，应符合下列规定：",
            "text": "",
            "page_start": 15,
            "page_end": 15,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert blocks[0].clause_no == "4"


def test_build_single_standard_blocks_keeps_split_clause_title_out_of_numbered_list_merge() -> None:
    sections = [
        {
            "id": "s-host",
            "section_code": "4.2.2",
            "title": "充气运输的变压器、电抗器应符合下列规定：",
            "text": "",
            "page_start": 18,
            "page_end": 18,
        },
        {
            "id": "s-host-1",
            "section_code": "1",
            "title": "应安装储油柜及吸湿器，注以合格油至储油柜规定油位。",
            "text": "",
            "page_start": 18,
            "page_end": 18,
        },
        {
            "id": "s-host-2",
            "section_code": "2",
            "title": "当不能及时注油时，应继续充与原充气体相同的气体保管。",
            "text": "",
            "page_start": 18,
            "page_end": 18,
        },
        {
            "id": "s-clause",
            "section_code": "4",
            "title": "2.4设备在保管期间，应经常检查。其变压器内油样性能应符合表4.2.4的规定：",
            "text": "表4.2.4变压器内油样性能\n<table><tr><td>试验项目</td><td>标准值</td></tr></table>",
            "page_start": 18,
            "page_end": 18,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert len(blocks) == 2
    assert blocks[0].clause_no == "4.2.2"
    assert "1 应安装储油柜及吸湿器" in blocks[0].text
    assert "2 当不能及时注油时" in blocks[0].text
    assert blocks[1].clause_no == "4.2.4"
    assert blocks[1].segment_type == "normative_clause_block"
    assert blocks[1].text.startswith("设备在保管期间，应经常检查。")
    assert "表4.2.4变压器内油样性能" in blocks[1].text


def test_build_single_standard_blocks_keeps_normative_heading_with_appendix_reference_out_of_appendix_bucket() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "4.7.1",
            "title": "变压器、电抗器是否需要进行干燥，应根据本规范附录A进行综合分析判断后确定。",
            "text": "",
            "page_start": 25,
            "page_end": 25,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert blocks[0].clause_no == "4.7.1"
    assert blocks[0].segment_type == "normative_clause_block"
    assert blocks[0].text == "变压器、电抗器是否需要进行干燥，应根据本规范附录A进行综合分析判断后确定。"


def test_build_single_standard_blocks_treats_sentence_like_clause_title_as_text() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "1.0.1",
            "title": "为保证电力变压器、油浸电抗器及互感器的施工安装质量，促进安装技术进步，确保设备安全运行，制定本规范。",
            "text": "",
            "page_start": 10,
            "page_end": 10,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert blocks[0].segment_type == "normative_clause_block"
    assert blocks[0].clause_no == "1.0.1"
    assert blocks[0].text == "为保证电力变压器、油浸电抗器及互感器的施工安装质量，促进安装技术进步，确保设备安全运行，制定本规范。"


def test_build_single_standard_blocks_merges_numbered_list_items_into_previous_clause() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "4.1.2",
            "title": "变压器或电抗器的装卸应符合下列规定：",
            "text": "",
            "page_start": 15,
            "page_end": 15,
        },
        {
            "id": "s2",
            "section_code": "1",
            "title": "装卸站台、码头等地点的地面应坚实。",
            "text": "",
            "page_start": 15,
            "page_end": 15,
        },
        {
            "id": "s3",
            "section_code": "2",
            "title": "装卸时应设专人观测车辆、平台的升降或船只的沉浮情",
            "text": "况，防止超过允许范围的倾斜。",
            "page_start": 15,
            "page_end": 15,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert len(blocks) == 1
    assert blocks[0].segment_type == "normative_clause_block"
    assert blocks[0].clause_no == "4.1.2"
    assert "1 装卸站台、码头等地点的地面应坚实。" in blocks[0].text
    assert "2 装卸时应设专人观测车辆、平台的升降或船只的沉浮情况，防止超过允许范围的倾斜。" in blocks[0].text
    assert blocks[0].section_ids == ["s1", "s2", "s3"]
    assert blocks[0].source_refs == [
        "document_section:s1",
        "document_section:s2",
        "document_section:s3",
    ]


def test_build_single_standard_blocks_marks_non_clause_tail_sections_and_commentary_region() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": None,
            "title": "本规范用词说明",
            "text": "1 为便于在执行本规范条文时区别对待。",
            "page_start": 39,
            "page_end": 39,
        },
        {
            "id": "s2",
            "section_code": None,
            "title": "引用标准名录",
            "text": "",
            "page_start": 40,
            "page_end": 40,
        },
        {
            "id": "s3",
            "section_code": None,
            "title": "修订说明",
            "text": "",
            "page_start": 42,
            "page_end": 42,
        },
        {
            "id": "s4",
            "section_code": "2",
            "title": "术语",
            "text": "",
            "page_start": 45,
            "page_end": 45,
        },
        {
            "id": "s5",
            "section_code": "4.1.7",
            "title": "为确保运输安全此条规定为强制性条文。",
            "text": "",
            "page_start": 46,
            "page_end": 46,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert [block.segment_type for block in blocks] == [
        "non_clause_block",
        "non_clause_block",
        "non_clause_block",
        "non_clause_block",
        "commentary_block",
    ]
    assert blocks[-1].clause_no == "4.1.7"
    assert blocks[-1].text == "为确保运输安全此条规定为强制性条文。"


def test_build_single_standard_blocks_detects_commentary_tail_from_cover_text_and_marks_inline_commentary_chapter() -> None:
    sections = [
        {
            "id": "cover",
            "section_code": None,
            "title": "电气装置安装工程电缆线路施工及验收标准",
            "text": "GB 50168-2018\n\n条文说明",
            "page_start": 47,
            "page_end": 47,
        },
        {
            "id": "intro",
            "section_code": None,
            "title": "编制说明",
            "text": "本标准是在上一版基础上修订而成。",
            "page_start": 48,
            "page_end": 48,
        },
        {
            "id": "commentary",
            "section_code": None,
            "title": "5.1电缆导管的加工与敷设",
            "text": (
                "5.1.1本条提出了对电缆管选材的基本要求。\n"
                "5.1.2对本条的规定说明如下。"
            ),
            "page_start": 54,
            "page_end": 54,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert [block.segment_type for block in blocks] == [
        "non_clause_block",
        "non_clause_block",
        "commentary_block",
    ]
    assert blocks[2].clause_no == "5.1"


def test_build_single_standard_blocks_does_not_merge_wording_note_tail_into_appendix() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "A.0.2",
            "title": "充气运输的变压器及电抗器应符合现行国家标准的规定，并应符合下列规定。",
            "text": "",
            "page_start": 38,
            "page_end": 38,
        },
        {
            "id": "s2",
            "section_code": "1",
            "title": "器身内压力在出厂至安装前均应保持正压。",
            "text": "",
            "page_start": 38,
            "page_end": 38,
        },
        {
            "id": "s3",
            "section_code": "1",
            "title": "为便于在执行本规范条文时区别对待，对要求严格程度不同的用词说明如下：",
            "text": "1)表示很严格，非这样做不可的：",
            "page_start": 39,
            "page_end": 39,
        },
    ]

    blocks = build_single_standard_blocks(sections, [])

    assert [block.segment_type for block in blocks] == [
        "appendix_block",
        "non_clause_block",
    ]
    assert "器身内压力在出厂至安装前均应保持正压。" in blocks[0].text
    assert "为便于在执行本规范条文时区别对待" not in blocks[0].text
    assert "为便于在执行本规范条文时区别对待" in blocks[1].text
