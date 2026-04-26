from __future__ import annotations

import threading
from uuid import uuid4

from tender_backend.services.norm_service import norm_processor
from tender_backend.services.norm_service.block_segments import BlockSegment
from tender_backend.services.norm_service.scope_splitter import ProcessingScope


def test_index_clauses_succeeds_from_thread_without_event_loop(monkeypatch) -> None:
    calls: list[tuple[str, list[tuple[str, dict]]]] = []

    class FakeIndexManager:
        async def bulk_index(self, index: str, docs: list[tuple[str, dict]]) -> int:
            calls.append((index, docs))
            return len(docs)

    monkeypatch.setattr(norm_processor, "IndexManager", FakeIndexManager)
    monkeypatch.setattr(
        norm_processor.asyncio,
        "get_event_loop",
        lambda: (_ for _ in ()).throw(RuntimeError("There is no current event loop")),
    )
    monkeypatch.setattr(
        norm_processor,
        "build_clause_index_docs",
        lambda standard, clauses: [("doc-1", {"standard_id": str(standard["id"])})],
    )

    error: list[Exception] = []

    def worker() -> None:
        try:
            norm_processor._index_clauses(
                {"id": uuid4(), "standard_code": "GB 50148-2010", "standard_name": "测试规范"},
                [{"id": uuid4(), "clause_no": "4.7.2"}],
            )
        except Exception as exc:  # pragma: no cover - failure path for assertion
            error.append(exc)

    thread = threading.Thread(target=worker, name="norm-index-test")
    thread.start()
    thread.join()

    assert error == []
    assert len(calls) == 1
    assert calls[0][0] == "clause_index"


def test_collect_outline_clause_nos_recovers_compact_heading_codes() -> None:
    sections = [
        {"section_code": None, "title": "2术 语"},
        {"section_code": None, "title": "6.6岩石基础"},
        {"section_code": None, "title": "3.5.3金具的质量应符合国家现行标准的规定。"},
        {"section_code": "8.4", "title": "连接"},
    ]

    assert norm_processor._collect_outline_clause_nos(sections) == {"2", "6.6", "3.5.3", "8.4"}


def test_deterministic_entries_from_block_keeps_long_normative_clause_with_list_text() -> None:
    block = BlockSegment(
        segment_type="normative_clause_block",
        chapter_label="3.1.1 架空电力线路工程使用的原材料及器材应符合下列规定：",
        text=(
            "架空电力线路工程使用的原材料及器材应符合下列规定：\n"
            "1 应有该批产品出厂质量检验合格证书。\n"
            "2 应有符合国家现行标准的各项质量检验资料。"
        ),
        clause_no="3.1.1",
        page_start=8,
        page_end=8,
        source_refs=["document_section:s1"],
        confidence="high",
    )

    entries = norm_processor._deterministic_entries_from_block(block)

    assert entries == [
        {
            "clause_no": "3.1.1",
            "clause_title": None,
            "clause_text": (
                "架空电力线路工程使用的原材料及器材应符合下列规定：\n"
                "1 应有该批产品出厂质量检验合格证书。\n"
                "2 应有符合国家现行标准的各项质量检验资料。"
            ),
            "summary": None,
            "tags": [],
            "page_start": 8,
            "page_end": 8,
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": "document_section:s1",
            "source_refs": ["document_section:s1"],
            "source_label": "3.1.1 架空电力线路工程使用的原材料及器材应符合下列规定：",
        },
    ]


def test_deterministic_entries_from_block_keeps_appendix_host_with_clause_text() -> None:
    block = BlockSegment(
        segment_type="appendix_block",
        chapter_label="B.0.1杆上电力变压器交接试验报告应符合表B.0.1的规定。",
        text="工程名称：\n安装位置：杆上",
        clause_no="B.0.1",
        page_start=41,
        page_end=41,
        source_refs=["document_section:s2"],
        confidence="medium",
    )

    entries = norm_processor._deterministic_entries_from_block(block)

    assert entries == [
        {
            "clause_no": "B.0.1",
            "clause_title": None,
            "clause_text": "工程名称：\n安装位置：杆上",
            "summary": None,
            "tags": [],
            "page_start": 41,
            "page_end": 41,
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": "document_section:s2",
            "source_refs": ["document_section:s2"],
            "source_label": "B.0.1杆上电力变压器交接试验报告应符合表B.0.1的规定。",
        },
    ]


def test_supplement_scope_entries_with_deterministic_inline_recovers_compact_embedded_clauses() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="8.6附件安装",
        text=(
            "8.6.1导线的固定应牢固、可靠。\n"
            "8.6.210kV及以下架空电力线路的裸铝导线在蝶式绝缘子上作耐张且采用绑扎方式固定时，应符合表8.6.2的规定。\n"
            "1.6.410kV及以下架空电力线路的引流线之间、引流线与主干线之间的连接，应符合下列规定：\n"
            "8.6.5绑扎用的绑线，应选用与导线同金属的单股线。\n"
            "8.6.63kV～10kV架空电力线路的引下线与3kV以下线路导线之间的距离，不宜小于200mm。\n"
            "8.6.10安装悬式、蝴蝶式绝缘子时，绝缘子安装应牢固。8.6.11金具的镀锌层有局部碰损、剥落或缺锌时，应除锈后补刷防锈漆。"
        ),
        page_start=29,
        page_end=29,
        source_refs=["document_section:s8_6"],
    )
    direct_entries = [
        {
            "clause_no": "8.6",
            "clause_title": None,
            "clause_text": scope.text,
            "summary": None,
            "tags": [],
            "page_start": 29,
            "page_end": 29,
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": "document_section:s8_6",
            "source_refs": ["document_section:s8_6"],
            "source_label": "8.6附件安装",
        }
    ]

    supplemented = norm_processor._supplement_scope_entries_with_deterministic_inline(
        scope,
        direct_entries,
        allowed_clause_nos={"8.6.1", "8.6.2", "8.6.4", "8.6.5", "8.6.6", "8.6.10", "8.6.11"},
    )

    assert [entry["clause_no"] for entry in supplemented] == [
        "8.6.1",
        "8.6.2",
        "8.6.4",
        "8.6.5",
        "8.6.6",
        "8.6.10",
        "8.6.11",
        "8.6",
    ]


def test_deterministic_inline_clause_entries_from_scope_recovers_ocr_prefixed_first_clause() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="6.6岩石基础",
        text=(
            "16.6.1岩石基础施工时,应逐基逐腿与设计地质资料核对。\n"
            "6.6.2岩石基础的开挖或钻孔应符合下列规定："
        ),
        page_start=16,
        page_end=16,
        source_refs=["document_section:s6_6"],
    )

    entries = norm_processor._deterministic_inline_clause_entries_from_scope(
        scope,
        allowed_clause_nos={"6.6.1", "6.6.2"},
    )

    assert [entry["clause_no"] for entry in entries] == ["6.6", "6.6.1", "6.6.2"]


def test_deterministic_inline_clause_entries_from_commentary_scope_recovers_nested_commentary_clauses() -> None:
    scope = ProcessingScope(
        scope_type="commentary",
        chapter_label="5.1电缆导管的加工与敷设",
        text=(
            "5.1.1本条提出了对电缆管选材的基本要求。\n"
            "5.1.2对本条的规定说明如下：\n"
            "1 管口应无毛刺。"
        ),
        page_start=54,
        page_end=54,
        source_refs=["document_section:s5_1_commentary"],
    )

    entries = norm_processor._deterministic_inline_clause_entries_from_scope(
        scope,
        allowed_clause_nos={"5.1.1", "5.1.2"},
    )

    assert [entry["clause_no"] for entry in entries] == ["5.1.1", "5.1.2"]
    assert all(entry["clause_type"] == "commentary" for entry in entries)


def test_deterministic_entries_from_commentary_host_block_defers_to_inline_clause_split() -> None:
    block = BlockSegment(
        segment_type="commentary_block",
        chapter_label="5.1电缆导管的加工与敷设",
        text=(
            "5.1.1本条提出了对电缆管选材的基本要求。\n"
            "5.1.2对本条的规定说明如下。"
        ),
        clause_no="5.1",
        page_start=54,
        page_end=54,
        source_refs=["document_section:s5_1_commentary"],
        confidence="high",
    )

    entries = norm_processor._deterministic_entries_from_block(block)

    assert entries == []


def test_deterministic_inline_clause_entries_from_scope_rejects_decimal_measurement_continuations() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="5.1电缆导管的加工与敷设",
        text=(
            "5.1.3电缆管的内径与穿入电缆外径之比不得小于\n"
            "1.5。\n"
            "5.1.4每根电缆管的弯头不应超过三个，直角弯不应超过两个。\n"
            "5.1.8电缆线芯连接金具，其截面宜为线芯截面的\n"
            "1.5倍。采取压接时，压接钳和模具应符合规格要求。"
        ),
        page_start=17,
        page_end=17,
        source_refs=["document_section:s5_1"],
    )

    entries = norm_processor._deterministic_inline_clause_entries_from_scope(
        scope,
        allowed_clause_nos={"5.1.3", "5.1.4", "5.1.8"},
    )

    assert [entry["clause_no"] for entry in entries] == ["5.1", "5.1.3", "5.1.4", "5.1.8"]


def test_should_skip_block_for_ai_skips_sparse_header_only_table_block() -> None:
    block = BlockSegment(
        segment_type="table_requirement_block",
        chapter_label="表格: 表6.1.9电缆最大牵引强度",
        text="表6.1.9电缆最大牵引强度",
        table_title="表6.1.9电缆最大牵引强度",
        table_html=(
            "<table>"
            "<tr><td>牵引方式</td></tr>"
            "<tr><td>受力部位</td></tr>"
            "<tr><td>允许牵引强度</td></tr>"
            "</table>"
        ),
        page_start=24,
        page_end=24,
        source_refs=["table:t-sparse"],
        confidence="medium",
    )

    assert norm_processor._deterministic_entries_from_block(block) == []
    assert norm_processor._should_skip_block_for_ai(block) is True


def test_appendix_block_deterministic_path_does_not_supplement_table_cell_noise() -> None:
    block = BlockSegment(
        segment_type="appendix_block",
        chapter_label="D.0.6 填写。",
        text=(
            "填写。\n"
            "表D.0.6 铁塔基础成型检查记录表\n"
            "<table><tr><td>A</td><td>B</td><td>C</td><td>D</td></tr>"
            "<tr><td>AB:</td><td>BC:</td><td>CD:</td><td>DA:</td></tr></table>"
        ),
        clause_no="D.0.6",
        page_start=49,
        page_end=49,
        source_refs=["document_section:d06"],
        confidence="high",
    )
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label=block.chapter_label,
        text=block.text,
        page_start=49,
        page_end=49,
        source_refs=block.source_refs,
    )

    entries = norm_processor._deterministic_entries_from_block(block)
    if norm_processor._should_supplement_direct_scope_entries(scope, block):
        entries = norm_processor._supplement_scope_entries_with_deterministic_inline(
            scope,
            entries,
            allowed_clause_nos={"D.0.6", "B", "C"},
        )

    assert [entry["clause_no"] for entry in entries] == ["D.0.6"]


def test_appendix_block_deterministic_path_does_not_promote_voltage_prefix_to_fake_clause() -> None:
    block = BlockSegment(
        segment_type="appendix_block",
        chapter_label="C.0.1 66kV及以下架空送电线路施工工程类别划分应符合表C.0.1的规定。",
        text=(
            "66kV及以下架空送电线路施工工程类别划分应符合表C.0.1的规定。\n"
            "表C.0.166kV及以下架空送电线路施工工程类别划分\n"
            "<table><tr><td>1.路径复测</td></tr></table>"
        ),
        clause_no="C.0.1",
        page_start=49,
        page_end=49,
        source_refs=["document_section:c01"],
        confidence="high",
    )
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label=block.chapter_label,
        text=block.text,
        page_start=49,
        page_end=49,
        source_refs=block.source_refs,
    )

    entries = norm_processor._deterministic_entries_from_block(block)
    if norm_processor._should_supplement_direct_scope_entries(scope, block):
        entries = norm_processor._supplement_scope_entries_with_deterministic_inline(
            scope,
            entries,
            allowed_clause_nos={"C.0.1", "66"},
        )

    assert [entry["clause_no"] for entry in entries] == ["C.0.1"]


def test_apply_scope_defaults_collapses_repeated_terminal_punctuation() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="8.6.2 表8.6.2绑扎长度值中增加了绝缘线的规定。。",
        text="表8.6.2绑扎长度值中增加了绝缘线的规定。。",
        page_start=86,
        page_end=86,
        source_refs=["document_section:s8_6_2"],
    )
    entry = {
        "clause_no": "8.6.2",
        "clause_text": "表8.6.2绑扎长度值中增加了绝缘线的规定。。",
    }

    norm_processor._apply_scope_defaults(entry, scope)

    assert entry["clause_text"] == "表8.6.2绑扎长度值中增加了绝缘线的规定。"


def test_sanitize_scope_entries_collapses_repeated_terminal_punctuation() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="8.6.2 表8.6.2绑扎长度值中增加了绝缘线的规定。。",
        text="表8.6.2绑扎长度值中增加了绝缘线的规定。。",
        page_start=86,
        page_end=86,
        source_refs=["document_section:s8_6_2"],
    )
    entries = [{
        "clause_no": "8.6.2",
        "clause_text": "表8.6.2绑扎长度值中增加了绝缘线的规定。。",
    }]

    sanitized = norm_processor._sanitize_scope_entries(scope, entries, allowed_clause_nos={"8.6.2"})

    assert sanitized[0]["clause_text"] == "表8.6.2绑扎长度值中增加了绝缘线的规定。"
