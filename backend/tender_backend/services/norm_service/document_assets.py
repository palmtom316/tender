"""Helpers for preserving structured parse assets on document records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class PageAsset:
    page_number: int | None
    normalized_text: str | None
    raw_page: dict[str, Any] | None
    source_ref: str


@dataclass(frozen=True)
class TableAsset:
    source_ref: str
    page_start: int | None
    page_end: int | None
    table_title: str | None
    table_html: str | None
    raw_json: dict[str, Any] | None


@dataclass(frozen=True)
class DocumentAsset:
    document_id: UUID
    parser_name: str | None
    parser_version: str | None
    raw_payload: dict[str, Any]
    pages: list[PageAsset]
    tables: list[TableAsset]
    full_markdown: str


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _pages_from_raw_payload(raw_payload: dict[str, Any]) -> list[PageAsset]:
    raw_pages = raw_payload.get("pages")
    if not isinstance(raw_pages, list):
        return []
    pages: list[PageAsset] = []
    for index, item in enumerate(raw_pages):
        raw_page = item if isinstance(item, dict) else None
        page_number = raw_page.get("page_number") if raw_page else None
        markdown = raw_page.get("markdown") if raw_page else None
        pages.append(
            PageAsset(
                page_number=page_number,
                normalized_text=markdown,
                raw_page=raw_page,
                source_ref=f"document.raw_payload.pages[{index}]",
            )
        )
    return pages


def _build_pages_from_sections(sections: list[dict]) -> list[PageAsset]:
    pages: list[PageAsset] = []
    for section in sections:
        raw_json = section.get("raw_json")
        raw_page = raw_json if isinstance(raw_json, dict) else None
        page_number = (raw_page or {}).get("page_number") or section.get("page_start")
        markdown = (raw_page or {}).get("markdown") or section.get("text")
        if page_number is None and not markdown:
            continue
        section_id = section.get("id")
        source_ref = f"document_section:{section_id}" if section_id is not None else "document_section:unknown"
        pages.append(
            PageAsset(
                page_number=page_number,
                normalized_text=markdown,
                raw_page=raw_page,
                source_ref=source_ref,
            )
        )
    return pages


def _tables_from_raw_payload(raw_payload: dict[str, Any]) -> list[TableAsset]:
    raw_tables = raw_payload.get("tables")
    if not isinstance(raw_tables, list):
        return []
    tables: list[TableAsset] = []
    for index, item in enumerate(raw_tables):
        raw_json = item if isinstance(item, dict) else None
        page = (raw_json or {}).get("page")
        page_start = (raw_json or {}).get("page_start", page)
        page_end = (raw_json or {}).get("page_end", page)
        tables.append(
            TableAsset(
                source_ref=f"document.raw_payload.tables[{index}]",
                page_start=page_start,
                page_end=page_end,
                table_title=(raw_json or {}).get("table_title") or (raw_json or {}).get("title"),
                table_html=(raw_json or {}).get("table_html") or (raw_json or {}).get("html"),
                raw_json=raw_json,
            )
        )
    return tables


def _build_tables_from_rows(tables: list[dict]) -> list[TableAsset]:
    structured_tables: list[TableAsset] = []
    for table in tables:
        raw_json = table.get("raw_json")
        raw_json_dict = raw_json if isinstance(raw_json, dict) else None
        page = table.get("page")
        page_start = table.get("page_start", page)
        page_end = table.get("page_end", page)
        table_id = table.get("id")
        structured_tables.append(
            TableAsset(
                source_ref=f"table:{table_id}" if table_id is not None else "table:unknown",
                page_start=page_start,
                page_end=page_end,
                table_title=table.get("table_title"),
                table_html=table.get("table_html"),
                raw_json=raw_json_dict,
            )
        )
    return structured_tables


def build_document_asset(
    *,
    document_id: UUID,
    document: dict | None,
    sections: list[dict],
    tables: list[dict],
) -> DocumentAsset:
    existing_raw_payload = (document or {}).get("raw_payload")
    normalized_payload = dict(existing_raw_payload) if isinstance(existing_raw_payload, dict) else {}

    page_assets = _pages_from_raw_payload(normalized_payload)
    if not page_assets:
        page_assets = _build_pages_from_sections(sections)
        normalized_payload["pages"] = [
            {"page_number": page.page_number, "markdown": page.normalized_text}
            for page in page_assets
        ]

    table_assets = _tables_from_raw_payload(normalized_payload)
    if not table_assets:
        table_assets = _build_tables_from_rows(tables)
        normalized_payload["tables"] = [
            asset.raw_json
            if asset.raw_json is not None
            else {
                "page_start": asset.page_start,
                "page_end": asset.page_end,
                "table_title": asset.table_title,
                "table_html": asset.table_html,
            }
            for asset in table_assets
        ]

    full_markdown = normalized_payload.get("full_markdown")
    if not isinstance(full_markdown, str):
        full_markdown = "\n\n".join(
            str(page.normalized_text).strip()
            for page in page_assets
            if page.normalized_text
        )
        normalized_payload["full_markdown"] = full_markdown

    return DocumentAsset(
        document_id=_coerce_uuid((document or {}).get("id") or document_id),
        parser_name=(document or {}).get("parser_name"),
        parser_version=(document or {}).get("parser_version"),
        raw_payload=normalized_payload,
        pages=page_assets,
        tables=table_assets,
        full_markdown=full_markdown,
    )


def serialize_document_asset(asset: DocumentAsset | None) -> dict[str, Any] | None:
    if asset is None:
        return None
    raw_payload = dict(asset.raw_payload)
    raw_payload["pages"] = [
        {
            "page_number": page.page_number,
            "markdown": page.normalized_text,
            "raw_page": page.raw_page,
            "source_ref": page.source_ref,
        }
        for page in asset.pages
    ]
    raw_payload["tables"] = [
        {
            "source_ref": table.source_ref,
            "page_start": table.page_start,
            "page_end": table.page_end,
            "table_title": table.table_title,
            "table_html": table.table_html,
            "raw_json": table.raw_json,
        }
        for table in asset.tables
    ]
    raw_payload["full_markdown"] = asset.full_markdown
    return {
        "id": asset.document_id,
        "document_id": asset.document_id,
        "parser_name": asset.parser_name,
        "parser_version": asset.parser_version,
        "raw_payload": raw_payload,
    }
