"""Helpers for preserving structured parse assets on document records."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from uuid import UUID


_TABLE_TITLE_LINE_RE = re.compile(r"^\s*(表\s*[A-Za-z]?\d+(?:\.\d+)*\s+\S[^\n]*)\s*$", re.MULTILINE)


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
    """Return canonical PageAssets from a raw_payload.

    Only dicts shaped like `{page_number: int, markdown: non-empty str}` are
    accepted. Legacy layout blocks (`{type, content}`) and pipeline-backend
    residue (`{preproc_blocks: [...]}`) are silently dropped so the caller can
    decide whether to fall back to section-derived pages.
    """
    raw_pages = raw_payload.get("pages")
    if not isinstance(raw_pages, list):
        return []
    pages: list[PageAsset] = []
    for index, item in enumerate(raw_pages):
        if not isinstance(item, dict):
            continue
        page_number = item.get("page_number")
        markdown = item.get("markdown")
        if (
            not isinstance(page_number, int)
            or page_number <= 0
            or not isinstance(markdown, str)
            or not markdown.strip()
        ):
            continue
        pages.append(
            PageAsset(
                page_number=page_number,
                normalized_text=markdown,
                raw_page=item,
                source_ref=f"document.raw_payload.pages[{index}]",
            )
        )
    return pages


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).split())


def _table_image_path(raw_json: dict[str, Any] | None) -> str:
    value = (raw_json or {}).get("image_path")
    if not isinstance(value, str):
        return ""
    return value.strip()


def _build_section_markdown(section: dict, raw_page: dict[str, Any] | None) -> str | None:
    raw_markdown = (raw_page or {}).get("markdown")
    if isinstance(raw_markdown, str) and raw_markdown.strip():
        return raw_markdown

    code = str(section.get("section_code") or "").strip()
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or section.get("body") or "").strip()
    heading = f"{code} {title}".strip()
    if heading and text:
        return f"{heading}\n{text}"
    if heading:
        return heading
    if text:
        return text
    return None


def _reconcile_page_assets(raw_pages: list[PageAsset], section_pages: list[PageAsset]) -> list[PageAsset]:
    if not raw_pages or not section_pages:
        return raw_pages

    reconciled: list[PageAsset] = []
    unused_indexes = set(range(len(section_pages)))

    for raw_page in raw_pages:
        best_index: int | None = None
        best_score = -1
        raw_text = _normalize_text(raw_page.normalized_text)

        for section_index in list(unused_indexes):
            candidate = section_pages[section_index]
            score = 0
            if (
                raw_page.page_number is not None
                and candidate.page_number is not None
                and raw_page.page_number == candidate.page_number
            ):
                score += 2
            if raw_text and raw_text == _normalize_text(candidate.normalized_text):
                score += 2
            if score > best_score:
                best_score = score
                best_index = section_index

        if best_index is not None and best_score > 0:
            unused_indexes.discard(best_index)
            source_ref = section_pages[best_index].source_ref
        else:
            source_ref = raw_page.source_ref

        reconciled.append(
            PageAsset(
                page_number=raw_page.page_number,
                normalized_text=raw_page.normalized_text,
                raw_page=raw_page.raw_page,
                source_ref=source_ref,
            )
        )

    return reconciled


def _build_pages_from_sections(sections: list[dict]) -> list[PageAsset]:
    pages: list[PageAsset] = []
    for section in sections:
        raw_json = section.get("raw_json")
        raw_page = raw_json if isinstance(raw_json, dict) else None
        page_number = (raw_page or {}).get("page_number") or section.get("page_start")
        markdown = _build_section_markdown(section, raw_page)
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


def _reconcile_table_assets(raw_tables: list[TableAsset], row_tables: list[TableAsset]) -> list[TableAsset]:
    if not raw_tables or not row_tables:
        return raw_tables

    reconciled: list[TableAsset] = []
    unused_indexes = set(range(len(row_tables)))

    for raw_table in raw_tables:
        best_index: int | None = None
        best_score = -1
        raw_title = _normalize_text(raw_table.table_title)
        raw_html = _normalize_text(raw_table.table_html)
        raw_image_path = _table_image_path(raw_table.raw_json)

        for row_index in list(unused_indexes):
            candidate = row_tables[row_index]
            score = 0
            if (
                raw_table.page_start is not None
                and candidate.page_start is not None
                and raw_table.page_start == candidate.page_start
            ):
                score += 2
            if (
                raw_table.page_end is not None
                and candidate.page_end is not None
                and raw_table.page_end == candidate.page_end
            ):
                score += 1
            if raw_title and raw_title == _normalize_text(candidate.table_title):
                score += 2
            if raw_html and raw_html == _normalize_text(candidate.table_html):
                score += 3
            if raw_image_path and raw_image_path == _table_image_path(candidate.raw_json):
                score += 2
            if score > best_score:
                best_score = score
                best_index = row_index

        if best_index is not None and best_score > 0:
            unused_indexes.discard(best_index)
            matched_table = row_tables[best_index]
            source_ref = matched_table.source_ref
        else:
            matched_table = None
            source_ref = raw_table.source_ref

        reconciled.append(
            TableAsset(
                source_ref=source_ref,
                page_start=raw_table.page_start if raw_table.page_start is not None else (matched_table.page_start if matched_table else None),
                page_end=raw_table.page_end if raw_table.page_end is not None else (matched_table.page_end if matched_table else None),
                table_title=raw_table.table_title or (matched_table.table_title if matched_table else None),
                table_html=raw_table.table_html or (matched_table.table_html if matched_table else None),
                raw_json=raw_table.raw_json,
            )
        )

    return reconciled


def _extract_table_title_occurrences(pages: list[PageAsset]) -> list[tuple[int, str]]:
    occurrences: list[tuple[int, str]] = []
    for page in pages:
        if page.page_number is None:
            continue
        text = page.normalized_text
        if not isinstance(text, str) or not text.strip():
            continue
        for match in _TABLE_TITLE_LINE_RE.finditer(text):
            title = match.group(1).strip()
            if title:
                occurrences.append((page.page_number, title))
    return occurrences


def _backfill_table_pages_from_pages(tables: list[TableAsset], pages: list[PageAsset]) -> list[TableAsset]:
    if not tables or not pages:
        return tables

    title_occurrences = _extract_table_title_occurrences(pages)
    next_title_index = 0
    filled: list[TableAsset] = []
    for table in tables:
        if table.page_start is not None and table.page_end is not None:
            table_title = table.table_title
            while next_title_index < len(title_occurrences):
                title_page, inferred_title = title_occurrences[next_title_index]
                if title_page < table.page_start:
                    next_title_index += 1
                    continue
                if title_page == table.page_start:
                    if not table_title:
                        table_title = inferred_title
                    next_title_index += 1
                break
            filled.append(table)
            continue

        table_title = _normalize_text(table.table_title)
        table_html = _normalize_text(table.table_html)
        matched_page: int | None = None
        inferred_title: str | None = table.table_title
        for page in pages:
            page_text = _normalize_text(page.normalized_text)
            if not page_text or page.page_number is None:
                continue
            if table_html and table_html in page_text:
                matched_page = page.page_number
                break
            if table_title and table_title in page_text:
                matched_page = page.page_number
                break

        if matched_page is not None:
            while next_title_index < len(title_occurrences):
                title_page, title_text = title_occurrences[next_title_index]
                if title_page < matched_page:
                    next_title_index += 1
                    continue
                if title_page == matched_page:
                    if not inferred_title:
                        inferred_title = title_text
                    next_title_index += 1
                break

        if matched_page is None:
            while next_title_index < len(title_occurrences):
                title_page, title_text = title_occurrences[next_title_index]
                next_title_index += 1
                if title_page <= 0:
                    continue
                matched_page = title_page
                if not inferred_title:
                    inferred_title = title_text
                break

        if matched_page is None:
            filled.append(table)
            continue

        filled.append(
            TableAsset(
                source_ref=table.source_ref,
                page_start=matched_page,
                page_end=matched_page,
                table_title=inferred_title,
                table_html=table.table_html,
                raw_json=table.raw_json,
            )
        )

    return filled


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
    section_page_assets = _build_pages_from_sections(sections)
    if not page_assets:
        page_assets = section_page_assets
        normalized_payload["pages"] = [
            {"page_number": page.page_number, "markdown": page.normalized_text}
            for page in page_assets
        ]
    else:
        page_assets = _reconcile_page_assets(page_assets, section_page_assets)

    table_assets = _tables_from_raw_payload(normalized_payload)
    row_table_assets = _build_tables_from_rows(tables)
    if not table_assets:
        table_assets = row_table_assets
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
    else:
        table_assets = _reconcile_table_assets(table_assets, row_table_assets)
    table_assets = _backfill_table_pages_from_pages(table_assets, page_assets)

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
