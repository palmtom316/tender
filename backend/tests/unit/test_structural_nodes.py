from __future__ import annotations

from uuid import UUID

from tender_backend.services.norm_service.document_assets import DocumentAsset, PageAsset, TableAsset
from tender_backend.services.norm_service.scope_splitter import rebalance_scopes
from tender_backend.services.norm_service.structural_nodes import build_processing_scopes, build_structural_nodes


def test_build_structural_nodes_creates_page_and_table_nodes_with_source_refs() -> None:
    asset = DocumentAsset(
        document_id=UUID("11111111-1111-1111-1111-111111111111"),
        parser_name="mineru",
        parser_version="v1",
        raw_payload={},
        pages=[
            PageAsset(
                page_number=1,
                normalized_text="1 总则\n1.0.1 正文",
                raw_page=None,
                source_ref="document_section:s1",
            ),
            PageAsset(
                page_number=2,
                normalized_text="条文说明\n1.0.1 说明正文",
                raw_page=None,
                source_ref="document_section:s2",
            ),
        ],
        tables=[
            TableAsset(
                source_ref="table:t1",
                page_start=3,
                page_end=3,
                table_title="主要参数",
                table_html="<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
                raw_json={"id": "t1"},
            )
        ],
        full_markdown="1 总则\n1.0.1 正文\n\n条文说明\n1.0.1 说明正文",
    )

    nodes = build_structural_nodes(asset)

    assert [node.node_type for node in nodes] == ["page", "page", "table"]
    assert nodes[0].source_ref == "document_section:s1"
    assert nodes[1].source_ref == "document_section:s2"
    assert nodes[2].source_ref == "table:t1"
    assert nodes[2].table_title == "主要参数"


def test_build_processing_scopes_includes_structured_context_and_table_scope() -> None:
    asset = DocumentAsset(
        document_id=UUID("22222222-2222-2222-2222-222222222222"),
        parser_name="mineru",
        parser_version="v1",
        raw_payload={},
        pages=[
            PageAsset(
                page_number=1,
                normalized_text="1 总则\n1.0.1 正文",
                raw_page=None,
                source_ref="document_section:s1",
            ),
            PageAsset(
                page_number=2,
                normalized_text="条文说明\n1.0.1 说明正文",
                raw_page=None,
                source_ref="document_section:s2",
            ),
        ],
        tables=[
            TableAsset(
                source_ref="table:t1",
                page_start=2,
                page_end=2,
                table_title="主要参数",
                table_html="<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
                raw_json={"id": "t1"},
            )
        ],
        full_markdown="1 总则\n1.0.1 正文\n\n条文说明\n1.0.1 说明正文",
    )

    scopes = build_processing_scopes(asset)

    assert [scope.scope_type for scope in scopes] == ["normative", "commentary", "table"]

    normative = scopes[0]
    assert normative.source_refs == ["document_section:s1"]
    assert normative.context == {
        "document_id": "22222222-2222-2222-2222-222222222222",
        "source_refs": ["document_section:s1"],
        "node_types": ["page"],
    }

    commentary = scopes[1]
    assert commentary.source_refs == ["document_section:s2"]
    assert commentary.context == {
        "document_id": "22222222-2222-2222-2222-222222222222",
        "source_refs": ["document_section:s2"],
        "node_types": ["page"],
    }

    table_scope = scopes[2]
    assert table_scope.chapter_label == "表格: 主要参数"
    assert table_scope.source_refs == ["table:t1"]
    assert table_scope.context == {
        "document_id": "22222222-2222-2222-2222-222222222222",
        "source_ref": "table:t1",
        "node_type": "table",
        "table_title": "主要参数",
    }


def test_build_processing_scopes_narrows_page_range_to_matched_page_nodes() -> None:
    asset = DocumentAsset(
        document_id=UUID("44444444-4444-4444-4444-444444444444"),
        parser_name="mineru",
        parser_version="v1",
        raw_payload={},
        pages=[
            PageAsset(
                page_number=1,
                normalized_text="1 总则\n1.0.1 正文",
                raw_page=None,
                source_ref="document_section:s1",
            ),
            PageAsset(
                page_number=2,
                normalized_text="2 术语\n2.0.1 正文",
                raw_page=None,
                source_ref="document_section:s2",
            ),
        ],
        tables=[],
        full_markdown="1 总则\n1.0.1 正文\n\n2 术语\n2.0.1 正文",
    )

    scopes = build_processing_scopes(asset)

    assert [scope.chapter_label for scope in scopes] == ["1 总则", "2 术语"]
    assert scopes[0].page_start == 1
    assert scopes[0].page_end == 1
    assert scopes[1].page_start == 2
    assert scopes[1].page_end == 2


def test_build_structural_nodes_preserves_input_order_when_page_numbers_missing() -> None:
    asset = DocumentAsset(
        document_id=UUID("55555555-5555-5555-5555-555555555555"),
        parser_name="mineru",
        parser_version="v1",
        raw_payload={},
        pages=[
            PageAsset(
                page_number=None,
                normalized_text="1 总则\n1.0.1 正文",
                raw_page=None,
                source_ref="document_section:z-last",
            ),
            PageAsset(
                page_number=None,
                normalized_text="2 术语\n2.0.1 正文",
                raw_page=None,
                source_ref="document_section:a-first-lexicographically",
            ),
            PageAsset(
                page_number=None,
                normalized_text="3 基本规定\n3.0.1 正文",
                raw_page=None,
                source_ref="document_section:m-middle",
            ),
        ],
        tables=[],
        full_markdown="",
    )

    nodes = build_structural_nodes(asset)

    assert [node.source_ref for node in nodes] == [
        "document_section:z-last",
        "document_section:a-first-lexicographically",
        "document_section:m-middle",
    ]


def test_rebalance_scopes_filters_source_refs_by_child_text_segments() -> None:
    asset = DocumentAsset(
        document_id=UUID("33333333-3333-3333-3333-333333333333"),
        parser_name="mineru",
        parser_version="v1",
        raw_payload={},
        pages=[
            PageAsset(
                page_number=1,
                normalized_text="1 总则\n" + ("A" * 1600),
                raw_page=None,
                source_ref="document_section:s1",
            ),
            PageAsset(
                page_number=2,
                normalized_text="1.0.2\n" + ("B" * 1600),
                raw_page=None,
                source_ref="document_section:s2",
            ),
        ],
        tables=[],
        full_markdown="",
    )

    scopes = build_processing_scopes(asset)
    normative = scopes[0]
    assert normative.source_refs == ["document_section:s1", "document_section:s2"]
    assert len(normative.source_chunks) == 2

    rebalanced = rebalance_scopes([normative], max_chars=2200)

    assert len(rebalanced) == 2
    assert rebalanced[0].source_refs == ["document_section:s1"]
    assert rebalanced[1].source_refs == ["document_section:s2"]


def test_build_processing_scopes_uses_leaf_outline_boundaries_from_raw_pages() -> None:
    asset = DocumentAsset(
        document_id=UUID("66666666-6666-6666-6666-666666666666"),
        parser_name="mineru",
        parser_version="v1",
        raw_payload={
            "pages": [
                {
                    "page_number": 15,
                    "markdown": (
                        "4 电力变压器、油浸电抗器\n"
                        "4.1 装卸、运输与就位\n"
                        "4.1.1 条文正文\n"
                        "1 水路运输时，应做好下列工作："
                    ),
                },
                {
                    "page_number": 17,
                    "markdown": (
                        "4.2 交接与保管\n"
                        "4.2.1 设备到达现场后，应及时按下列规定进行外观检查："
                    ),
                },
                {
                    "page_number": 35,
                    "markdown": (
                        "5 互感器\n"
                        "5.1 一般规定\n"
                        "5.1.1 互感器运输和保管应符合产品技术文件的规定。"
                    ),
                },
                {
                    "page_number": 38,
                    "markdown": (
                        "附录A 新装电力变压器及油浸电抗器不需干燥的条件\n"
                        "A.0.1 带油运输的变压器及电抗器应符合下列规定："
                    ),
                },
                {
                    "page_number": 39,
                    "markdown": (
                        "本规范用词说明\n"
                        "为便于在执行本规范条文时区别对待，对要求严格程度不同的用词说明如下："
                    ),
                },
            ]
        },
        pages=[
            PageAsset(
                page_number=15,
                normalized_text=(
                    "4 电力变压器、油浸电抗器\n"
                    "4.1 装卸、运输与就位\n"
                    "4.1.1 条文正文\n"
                    "1 水路运输时，应做好下列工作："
                ),
                raw_page={"page_number": 15, "source_ref": "document.raw_payload.pages[0]"},
                source_ref="document.raw_payload.pages[0]",
            ),
            PageAsset(
                page_number=17,
                normalized_text=(
                    "4.2 交接与保管\n"
                    "4.2.1 设备到达现场后，应及时按下列规定进行外观检查："
                ),
                raw_page={"page_number": 17, "source_ref": "document.raw_payload.pages[1]"},
                source_ref="document.raw_payload.pages[1]",
            ),
            PageAsset(
                page_number=35,
                normalized_text=(
                    "5 互感器\n"
                    "5.1 一般规定\n"
                    "5.1.1 互感器运输和保管应符合产品技术文件的规定。"
                ),
                raw_page={"page_number": 35, "source_ref": "document.raw_payload.pages[2]"},
                source_ref="document.raw_payload.pages[2]",
            ),
            PageAsset(
                page_number=38,
                normalized_text=(
                    "附录A 新装电力变压器及油浸电抗器不需干燥的条件\n"
                    "A.0.1 带油运输的变压器及电抗器应符合下列规定："
                ),
                raw_page={"page_number": 38, "source_ref": "document.raw_payload.pages[3]"},
                source_ref="document.raw_payload.pages[3]",
            ),
            PageAsset(
                page_number=39,
                normalized_text=(
                    "本规范用词说明\n"
                    "为便于在执行本规范条文时区别对待，对要求严格程度不同的用词说明如下："
                ),
                raw_page={"page_number": 39, "source_ref": "document.raw_payload.pages[4]"},
                source_ref="document.raw_payload.pages[4]",
            ),
        ],
        tables=[],
        full_markdown="",
    )

    scopes = build_processing_scopes(asset)

    assert [scope.scope_type for scope in scopes] == ["normative", "normative", "normative", "normative", "commentary"]
    assert [scope.chapter_label for scope in scopes[:4]] == [
        "4.1 装卸、运输与就位",
        "4.2 交接与保管",
        "5.1 一般规定",
        "附录A 新装电力变压器及油浸电抗器不需干燥的条件",
    ]
    assert scopes[0].page_start == 15
    assert scopes[0].page_end == 15
    assert scopes[0].source_refs == ["document.raw_payload.pages[0]"]
    assert scopes[1].page_start == 17
    assert scopes[1].page_end == 17
    assert scopes[2].page_start == 35
    assert scopes[2].page_end == 35
    assert scopes[3].page_start == 38
    assert scopes[3].page_end == 38
    assert all("本规范用词说明" not in scope.text for scope in scopes[:4])
