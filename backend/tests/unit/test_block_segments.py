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
