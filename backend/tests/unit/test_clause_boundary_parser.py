from __future__ import annotations

from tender_backend.services.norm_service.clause_boundary_parser import parse_clause_blocks


def test_parse_clause_blocks_splits_numbered_clauses() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "3.1.1",
            "title": "变压器安装应符合设计要求。",
            "text": "",
            "page_start": 12,
            "page_end": 12,
        },
        {
            "id": "s2",
            "section_code": "3.1.2",
            "title": "附件安装不得遗漏。",
            "text": "",
            "page_start": 12,
            "page_end": 12,
        },
    ]

    blocks = parse_clause_blocks(sections, tables=[])

    assert [block["clause_no"] for block in blocks] == ["3.1.1", "3.1.2"]
    assert blocks[0]["block_type"] == "clause"
    assert blocks[0]["clause_text"] == "变压器安装应符合设计要求。"
    assert blocks[0]["source_refs"] == ["document_section:s1"]


def test_parse_clause_blocks_attaches_numbered_items_to_list_host() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "3.1.1",
            "title": "设备安装应符合下列要求：",
            "text": "",
            "page_start": 1,
            "page_end": 1,
        },
        {
            "id": "s2",
            "section_code": "1",
            "title": "基础应平整。",
            "text": "",
            "page_start": 1,
            "page_end": 1,
        },
    ]

    blocks = parse_clause_blocks(sections, tables=[])

    assert len(blocks) == 1
    assert blocks[0]["items"] == [
        {
            "node_type": "item",
            "node_label": "1",
            "clause_text": "基础应平整。",
            "source_refs": ["document_section:s2"],
        }
    ]


def test_parse_clause_blocks_supports_appendix_clause_numbers() -> None:
    sections = [
        {
            "id": "a1",
            "section_code": "A.0.1",
            "title": "检查记录应完整。",
            "text": "",
            "page_start": 30,
            "page_end": 30,
        }
    ]

    blocks = parse_clause_blocks(sections, tables=[])

    assert blocks[0]["clause_no"] == "A.0.1"
    assert blocks[0]["block_type"] == "appendix_clause"


def test_parse_clause_blocks_marks_commentary_tail() -> None:
    sections = [
        {
            "id": "h1",
            "section_code": None,
            "title": "条文说明",
            "text": "",
            "page_start": 40,
            "page_end": 40,
        },
        {
            "id": "c1",
            "section_code": "3.1.1",
            "title": "本条说明安装要求来源。",
            "text": "",
            "page_start": 41,
            "page_end": 41,
        },
    ]

    blocks = parse_clause_blocks(sections, tables=[])

    assert blocks == [
        {
            "block_id": "c1",
            "block_type": "commentary_clause",
            "clause_no": "3.1.1",
            "clause_text": "本条说明安装要求来源。",
            "page_start": 41,
            "page_end": 41,
            "source_refs": ["document_section:c1"],
            "confidence": "high",
            "items": [],
        }
    ]
