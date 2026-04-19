from uuid import uuid4

from tender_backend.services.parse_service.parser import update_document_parse_assets
from tender_backend.services.norm_service.document_assets import (
    DocumentAsset,
    PageAsset,
    TableAsset,
    build_document_asset,
)


def test_build_document_asset_reconciles_raw_payload_with_section_table_provenance() -> None:
    document_id = uuid4()
    section_id = uuid4()
    table_id = uuid4()
    document = {
        "id": document_id,
        "parser_name": "mineru",
        "parser_version": "v1",
        "raw_payload": {
            "batch_id": "batch-123",
            "pages": [{"page_number": 2, "markdown": "from raw payload"}],
            "tables": [{"page": 3, "title": "raw table", "html": "<table><tr><td>A</td></tr></table>"}],
            "full_markdown": "# raw markdown",
        },
    }
    sections = [
        {
            "id": section_id,
            "page_start": 10,
            "text": "from section",
            "raw_json": {"page_number": 10, "markdown": "from section markdown"},
        },
        {
            "id": section_id,
            "page_start": 2,
            "text": "from section",
            "raw_json": {"page_number": 2, "markdown": "from raw payload"},
        }
    ]
    tables = [
        {
            "id": table_id,
            "page": 11,
            "page_start": 3,
            "page_end": 3,
            "table_title": "raw table",
            "table_html": "<table><tr><td>A</td></tr></table>",
            "raw_json": {"page": 3, "title": "raw table", "html": "<table><tr><td>A</td></tr></table>"},
        }
    ]

    asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=sections,
        tables=tables,
    )

    assert asset is not None
    assert isinstance(asset, DocumentAsset)
    assert asset.document_id == document_id
    assert asset.raw_payload["batch_id"] == "batch-123"
    assert asset.full_markdown == "# raw markdown"
    assert len(asset.pages) == 1
    assert isinstance(asset.pages[0], PageAsset)
    assert asset.pages[0].page_number == 2
    assert asset.pages[0].normalized_text == "from raw payload"
    assert asset.pages[0].raw_page == {"page_number": 2, "markdown": "from raw payload"}
    assert asset.pages[0].source_ref == f"document_section:{section_id}"
    assert len(asset.tables) == 1
    assert isinstance(asset.tables[0], TableAsset)
    assert asset.tables[0].source_ref == f"table:{table_id}"
    assert asset.tables[0].raw_json == {
        "page": 3,
        "title": "raw table",
        "html": "<table><tr><td>A</td></tr></table>",
    }


def test_build_document_asset_keeps_raw_payload_provenance_when_rows_unavailable() -> None:
    document_id = uuid4()
    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [{"page_number": 2, "markdown": "from raw payload"}],
            "tables": [{"page": 3, "title": "raw table"}],
        },
    }

    asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=[],
        tables=[],
    )

    assert asset.pages[0].source_ref == "document.raw_payload.pages[0]"
    assert asset.tables[0].source_ref == "document.raw_payload.tables[0]"


def test_build_document_asset_does_not_force_position_match_when_evidence_missing() -> None:
    document_id = uuid4()
    section_id = uuid4()
    table_id = uuid4()
    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [{"page_number": 9, "markdown": "raw page text"}],
            "tables": [{"page": 12, "title": "raw table"}],
        },
    }
    sections = [
        {
            "id": section_id,
            "page_start": 4,
            "text": "different section text",
            "raw_json": {"page_number": 4, "markdown": "different section text"},
        }
    ]
    tables = [
        {
            "id": table_id,
            "page_start": 8,
            "page_end": 8,
            "table_title": "different table title",
            "table_html": "<table><tr><td>different</td></tr></table>",
            "raw_json": {"page": 8, "title": "different table title"},
        }
    ]

    asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=sections,
        tables=tables,
    )

    assert asset.pages[0].source_ref == "document.raw_payload.pages[0]"
    assert asset.tables[0].source_ref == "document.raw_payload.tables[0]"


def test_build_document_asset_falls_back_to_sections_and_tables_when_missing_in_raw_payload() -> None:
    document_id = uuid4()
    document = {
        "id": document_id,
        "parser_name": "mineru",
        "parser_version": "v1",
        "raw_payload": {"batch_id": "batch-123"},
    }
    sections = [
        {
            "id": uuid4(),
            "section_code": "3",
            "title": "总则",
            "page_start": 12,
            "text": "章节正文",
            "raw_json": {"page_number": 12, "markdown": "3 总则\n章节正文"},
        },
        {
            "id": uuid4(),
            "section_code": "4",
            "title": "术语",
            "page_start": 13,
            "text": "术语正文",
            "raw_json": {"page_number": 13, "markdown": "4 术语\n术语正文"},
        },
    ]
    tables = [
        {
            "id": uuid4(),
            "page": 13,
            "page_start": 13,
            "page_end": 13,
            "table_title": "主要参数",
            "table_html": "<table><tr><td>额定电压</td></tr></table>",
            "raw_json": {"page": 13, "title": "主要参数"},
        }
    ]

    asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=sections,
        tables=tables,
    )

    assert asset is not None
    assert isinstance(asset, DocumentAsset)
    assert asset.raw_payload["batch_id"] == "batch-123"
    assert [page.page_number for page in asset.pages] == [12, 13]
    assert [page.normalized_text for page in asset.pages] == ["3 总则\n章节正文", "4 术语\n术语正文"]
    assert [page.source_ref for page in asset.pages] == [
        f"document_section:{sections[0]['id']}",
        f"document_section:{sections[1]['id']}",
    ]
    assert asset.pages[0].raw_page == {"page_number": 12, "markdown": "3 总则\n章节正文"}
    assert len(asset.tables) == 1
    assert asset.tables[0].source_ref == f"table:{tables[0]['id']}"
    assert asset.tables[0].page_start == 13
    assert asset.tables[0].page_end == 13
    assert asset.tables[0].table_title == "主要参数"
    assert asset.tables[0].table_html.startswith("<table>")
    assert asset.tables[0].raw_json == {"page": 13, "title": "主要参数"}
    assert asset.full_markdown == "3 总则\n章节正文\n\n4 术语\n术语正文"


def test_build_document_asset_falls_back_to_sections_when_raw_pages_are_layout_blocks() -> None:
    document_id = uuid4()
    section_id = uuid4()
    document = {
        "id": document_id,
        "parser_name": "mineru",
        "raw_payload": {
            "pages": [
                {"type": "header", "content": "中华人民共和国国家标准"},
                {"type": "title", "content": "1 总则"},
            ],
            "full_markdown": "# 1 总则\n1.0.1 条文正文",
        },
    }
    sections = [
        {
            "id": section_id,
            "section_code": "1",
            "title": "总则",
            "text": "1.0.1 条文正文",
            "page_start": 1,
            "page_end": 1,
            "raw_json": {"page_number": 1},
        }
    ]

    asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=sections,
        tables=[],
    )

    assert len(asset.pages) == 1
    assert asset.pages[0].page_number == 1
    assert asset.pages[0].source_ref == f"document_section:{section_id}"
    assert asset.pages[0].normalized_text == "1 总则\n1.0.1 条文正文"


def test_build_document_asset_reads_canonical_pages_from_raw_payload() -> None:
    """Canonical raw_payload pages (page_number + markdown) must be consumed
    directly, without any section fallback dependency."""
    document_id = uuid4()
    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [{"page_number": 1, "markdown": "1 总则\n正文内容"}],
            "tables": [],
            "full_markdown": "1 总则\n正文内容",
        },
    }

    asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=[],
        tables=[],
    )

    assert len(asset.pages) == 1
    assert asset.pages[0].page_number == 1
    assert asset.pages[0].normalized_text == "1 总则\n正文内容"
    assert asset.pages[0].source_ref == "document.raw_payload.pages[0]"


def test_build_document_asset_ignores_noncanonical_page_entries_without_section_fallback() -> None:
    """Legacy-shape page entries (e.g. `{type, content}` layout blocks) must be
    discarded. When no sections exist to fall back to, pages must be empty —
    never a list of PageAssets with None page_number/text."""
    document_id = uuid4()
    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [{"type": "title", "content": "旧 shape"}],
            "tables": [],
            "full_markdown": "",
        },
    }

    asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=[],
        tables=[],
    )

    assert asset.pages == []


def test_build_document_asset_rejects_pipeline_backend_raw_payload() -> None:
    """Pipeline-backend residue (`preproc_blocks`) in raw_payload.pages is not
    a canonical page shape — it must be rejected and section fallback must
    take over."""
    document_id = uuid4()
    section_id = uuid4()
    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [
                {"preproc_blocks": [{"type": "text", "content": "legacy content"}]},
            ],
        },
    }
    sections = [
        {
            "id": section_id,
            "section_code": "1",
            "title": "总则",
            "page_start": 1,
            "page_end": 1,
            "text": "正文",
            "raw_json": {"page_number": 1},
        }
    ]

    asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=sections,
        tables=[],
    )

    assert len(asset.pages) == 1
    assert asset.pages[0].page_number == 1
    assert asset.pages[0].source_ref == f"document_section:{section_id}"
    assert asset.pages[0].normalized_text == "1 总则\n正文"


def test_update_document_parse_assets_serializes_document_asset_with_uuid_values() -> None:
    class _FakeCursor:
        def __init__(self) -> None:
            self.params = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def execute(self, _query, params) -> None:
            self.params = params

    class _FakeConn:
        def __init__(self) -> None:
            self._cursor = _FakeCursor()
            self.committed = False

        def cursor(self):
            return self._cursor

        def commit(self) -> None:
            self.committed = True

    document_id = uuid4()
    payload = build_document_asset(
        document_id=document_id,
        document={"id": document_id, "raw_payload": {"batch_id": "batch-123"}},
        sections=[],
        tables=[],
    )
    conn = _FakeConn()

    update_document_parse_assets(
        conn,  # type: ignore[arg-type]
        document_id=document_id,
        parser_name="mineru",
        parser_version="v1",
        raw_payload=payload,
    )

    assert conn.committed is True
    serialized_payload = conn._cursor.params[2]
    assert '"batch_id": "batch-123"' in serialized_payload
    assert '"document_id"' not in serialized_payload
    assert '"parser_name"' not in serialized_payload
    assert '"pages"' in serialized_payload


def test_build_document_asset_section_fallback_synthesizes_heading_when_raw_markdown_missing() -> None:
    document_id = uuid4()
    section_id = uuid4()
    asset = build_document_asset(
        document_id=document_id,
        document={"id": document_id, "raw_payload": {}},
        sections=[
            {
                "id": section_id,
                "section_code": "1",
                "title": "总则",
                "page_start": 1,
                "page_end": 1,
                "text": "1.0.1 正文",
                "raw_json": {"page_number": 1},
            }
        ],
        tables=[],
    )

    assert asset.pages[0].source_ref == f"document_section:{section_id}"
    assert asset.pages[0].normalized_text == "1 总则\n1.0.1 正文"


def test_build_document_asset_backfills_table_page_from_matching_page_text() -> None:
    document_id = uuid4()
    table_html = "<table><tr><td>试验项目</td><td>标准值</td></tr><tr><td>电气强度</td><td>≥70kV</td></tr></table>"
    asset = build_document_asset(
        document_id=document_id,
        document={
            "id": document_id,
            "raw_payload": {
                "pages": [
                    {"page_number": 18, "markdown": f"4.2.4 条文\n表 4.2.4 变压器内油样性能\n{table_html}"},
                ],
            },
        },
        sections=[],
        tables=[
            {
                "id": uuid4(),
                "page_start": None,
                "page_end": None,
                "table_title": "表 4.2.4 变压器内油样性能",
                "table_html": table_html,
                "raw_json": {},
            }
        ],
    )

    assert asset.tables[0].page_start == 18
    assert asset.tables[0].page_end == 18


def test_build_document_asset_reconciles_raw_table_with_row_by_html_and_image_path() -> None:
    document_id = uuid4()
    table_id = uuid4()
    table_html = "<table><tr><td>试验项目</td><td>标准值</td></tr><tr><td>电气强度</td><td>≥70kV</td></tr></table>"
    image_path = "abc123.jpg"

    asset = build_document_asset(
        document_id=document_id,
        document={
            "id": document_id,
            "raw_payload": {
                "tables": [
                    {
                        "html": table_html,
                        "image_path": image_path,
                    }
                ],
            },
        },
        sections=[],
        tables=[
            {
                "id": table_id,
                "page_start": None,
                "page_end": None,
                "table_title": None,
                "table_html": table_html,
                "raw_json": {"image_path": image_path},
            }
        ],
    )

    assert asset.tables[0].source_ref == f"table:{table_id}"


def test_build_document_asset_backfills_table_page_from_title_order_when_html_missing_from_page() -> None:
    document_id = uuid4()
    table_id = uuid4()
    table_html = (
        "<table><tr><td>试验项目</td><td>电压等级</td><td>标准值</td></tr>"
        "<tr><td>电气强度</td><td>750kV</td><td>≥70kV</td></tr></table>"
    )

    asset = build_document_asset(
        document_id=document_id,
        document={
            "id": document_id,
            "raw_payload": {
                "pages": [
                    {"page_number": 18, "markdown": "4.2.4 应符合表4.2.4的规定：\n表 4.2.4 变压器内油样性能"},
                    {"page_number": 19, "markdown": "4.3.1 见表4.3.1\n表 4.3.1 绝缘油取样数量"},
                ],
                "tables": [
                    {
                        "html": table_html,
                        "image_path": "abc123.jpg",
                    }
                ],
            },
        },
        sections=[],
        tables=[
            {
                "id": table_id,
                "page_start": None,
                "page_end": None,
                "table_title": None,
                "table_html": table_html,
                "raw_json": {"image_path": "abc123.jpg"},
            }
        ],
    )

    assert asset.tables[0].source_ref == f"table:{table_id}"
    assert asset.tables[0].page_start == 18
    assert asset.tables[0].page_end == 18
    assert asset.tables[0].table_title == "表 4.2.4 变压器内油样性能"
