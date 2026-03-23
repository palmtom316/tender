from uuid import uuid4

from tender_backend.services.parse_service.parser import update_document_parse_assets
from tender_backend.services.norm_service.document_assets import (
    DocumentAsset,
    PageAsset,
    TableAsset,
    build_document_asset,
)


def test_build_document_asset_prefers_raw_payload_pages_tables_and_full_markdown() -> None:
    document_id = uuid4()
    document = {
        "id": document_id,
        "parser_name": "mineru",
        "parser_version": "v1",
        "raw_payload": {
            "batch_id": "batch-123",
            "pages": [{"page_number": 2, "markdown": "from raw payload"}],
            "tables": [{"page": 3, "title": "raw table"}],
            "full_markdown": "# raw markdown",
        },
    }
    sections = [
        {
            "page_start": 10,
            "text": "from section",
            "raw_json": {"page_number": 10, "markdown": "from section markdown"},
        }
    ]
    tables = [
        {
            "page": 11,
            "table_title": "fallback table",
            "table_html": "<table></table>",
            "raw_json": {"page": 11, "title": "fallback table"},
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
    assert asset.pages[0].source_ref == "document.raw_payload.pages[0]"
    assert len(asset.tables) == 1
    assert isinstance(asset.tables[0], TableAsset)
    assert asset.tables[0].source_ref == "document.raw_payload.tables[0]"
    assert asset.tables[0].raw_json == {"page": 3, "title": "raw table"}


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
