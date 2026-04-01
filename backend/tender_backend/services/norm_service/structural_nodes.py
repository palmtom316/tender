"""Build structural nodes and processing scopes from parse assets."""

from __future__ import annotations

from dataclasses import dataclass
import re

from tender_backend.services.norm_service.document_assets import DocumentAsset
from tender_backend.services.norm_service.layout_compressor import PageWindow
from tender_backend.services.norm_service.outline_rebuilder import (
    collect_outline_markers_from_pages,
    normalize_outline_page_lines,
)
from tender_backend.services.norm_service.scope_splitter import (
    ProcessingScope,
    _split_by_chapters,
    split_into_scopes,
)

_COMMENTARY_BOUNDARY_LINES = ("附：条文说明", "附:条文说明", "条文说明")
_COMMENTARY_APPENDIX_ONLY_LINES = ("附：条文说明", "附:条文说明")
_NON_NORMATIVE_BACK_MATTER_LINES = ("本规范用词说明", "引用标准名录")
_CLAUSE_HEADING_PREFIX_RE = re.compile(r"^(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)")
_COMMENTARY_SCAN_MAX_LINES = 6


@dataclass(frozen=True)
class StructuralNode:
    node_type: str  # "page" | "table"
    source_ref: str
    text: str
    page_start: int
    page_end: int
    section_ids: list[str]
    table_title: str | None = None
    sort_index: int = 0


def _parse_section_id(source_ref: str) -> str | None:
    if source_ref.startswith("document_section:"):
        section_id = source_ref.split(":", 1)[1].strip()
        return section_id or None
    return None


def _stable_page(value: int | None) -> int:
    if isinstance(value, int):
        return value
    return 0


def _preferred_source_ref(default_ref: str, raw_payload: dict | None) -> str:
    raw_ref = (raw_payload or {}).get("source_ref")
    if isinstance(raw_ref, str) and raw_ref.strip():
        return raw_ref.strip()
    return default_ref


def build_structural_nodes(document_asset: DocumentAsset) -> list[StructuralNode]:
    nodes: list[StructuralNode] = []

    for index, page in enumerate(document_asset.pages):
        text = (page.normalized_text or "").strip()
        if not text:
            continue
        source_ref = _preferred_source_ref(page.source_ref, page.raw_page)
        section_id = _parse_section_id(source_ref)
        page_no = _stable_page(page.page_number)
        nodes.append(
            StructuralNode(
                node_type="page",
                source_ref=source_ref,
                text=text,
                page_start=page_no,
                page_end=page_no,
                section_ids=[section_id] if section_id else [],
                sort_index=index,
            )
        )

    for index, table in enumerate(document_asset.tables, start=len(document_asset.pages)):
        html = (table.table_html or "").strip()
        if not html:
            continue
        source_ref = _preferred_source_ref(table.source_ref, table.raw_json)
        nodes.append(
            StructuralNode(
                node_type="table",
                source_ref=source_ref,
                text=html,
                page_start=_stable_page(table.page_start),
                page_end=_stable_page(table.page_end if table.page_end is not None else table.page_start),
                section_ids=[],
                table_title=(table.table_title or "").strip() or None,
                sort_index=index,
            )
        )

    return sorted(
        nodes,
        key=lambda n: (
            n.page_start,
            1 if n.node_type == "table" else 0,
            n.sort_index,
            n.source_ref,
        ),
    )


def _dedupe_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _build_page_offsets(page_nodes: list[StructuralNode]) -> tuple[str, list[tuple[int, int, StructuralNode]]]:
    full_text_parts: list[str] = []
    offsets: list[tuple[int, int, StructuralNode]] = []
    cursor = 0
    for index, node in enumerate(page_nodes):
        if index > 0:
            cursor += 2  # "\n\n"
        full_text_parts.append(node.text)
        start = cursor
        end = start + len(node.text)
        offsets.append((start, end, node))
        cursor = end
    return "\n\n".join(full_text_parts), offsets


def _source_refs_for_scope(scope: ProcessingScope, page_nodes: list[StructuralNode]) -> list[StructuralNode]:
    if not page_nodes:
        return []

    full_text, offsets = _build_page_offsets(page_nodes)
    scope_text = scope.text.strip()
    if scope_text:
        start = full_text.find(scope_text)
        if start != -1:
            end = start + len(scope_text)
            return [
                node
                for node_start, node_end, node in offsets
                if node_end > start and node_start < end
            ]

    return [
        node
        for node in page_nodes
        if node.page_start <= scope.page_end and node.page_end >= scope.page_start
    ]


def _has_outline_child(markers, index: int) -> bool:
    current = markers[index].section_code
    prefix = f"{current}."
    return any(marker.section_code.startswith(prefix) for marker in markers[index + 1:])


def _apply_page_scope_metadata(
    scope: ProcessingScope,
    *,
    document_id: str,
    page_chunks: list[tuple[str, str]],
) -> ProcessingScope:
    scope.source_refs = _dedupe_in_order([source_ref for source_ref, _text in page_chunks])
    scope.context = {
        "document_id": document_id,
        "source_refs": scope.source_refs,
        "node_types": ["page" for _ in page_chunks],
    }
    scope.source_chunks = [
        {
            "text": text,
            "source_ref": source_ref,
            "node_type": "page",
        }
        for source_ref, text in page_chunks
    ]
    return scope


def _starts_commentary_appendix(lines: list[str]) -> bool:
    return _commentary_boundary_line_index(lines) is not None


def _commentary_boundary_line_index(lines: list[str]) -> int | None:
    scanned = 0
    for index, line in enumerate(lines):
        normalized = line.strip().replace(" ", "")
        if not normalized:
            continue
        scanned += 1
        if _is_commentary_boundary_heading(normalized):
            return index
        if scanned >= _COMMENTARY_SCAN_MAX_LINES:
            break
    return None


def _is_commentary_boundary_heading(normalized_line: str) -> bool:
    if normalized_line in _COMMENTARY_BOUNDARY_LINES:
        return True
    return normalized_line.endswith("条文说明") and not _CLAUSE_HEADING_PREFIX_RE.match(normalized_line)


def _strip_commentary_appendix_heading(lines: list[str]) -> list[str]:
    boundary_index = _commentary_boundary_line_index(lines)
    if boundary_index is None:
        return lines
    return lines[boundary_index + 1:]


def _is_non_normative_back_matter(lines: list[str]) -> bool:
    normalized_lines = [line.strip().replace(" ", "") for line in lines if line.strip()]
    if not normalized_lines:
        return False
    return normalized_lines[0] in _NON_NORMATIVE_BACK_MATTER_LINES


def _partition_pages(document_asset: DocumentAsset) -> tuple[list, list]:
    normative_pages: list = []
    commentary_pages: list = []
    commentary_started = False

    ordered_pages = sorted(
        document_asset.pages,
        key=lambda page: (
            page.page_number if isinstance(page.page_number, int) else 10**9,
            page.source_ref,
        ),
    )

    for page in ordered_pages:
        lines = normalize_outline_page_lines(page.normalized_text)
        if not lines:
            continue
        if not commentary_started and _starts_commentary_appendix(lines):
            commentary_started = True
        if commentary_started:
            commentary_pages.append(page)
        else:
            if _is_non_normative_back_matter(lines):
                continue
            normative_pages.append(page)

    return normative_pages, commentary_pages


def _build_outline_leaf_scopes(document_asset: DocumentAsset) -> list[ProcessingScope]:
    ordered_pages, _commentary_pages = _partition_pages(document_asset)
    markers = collect_outline_markers_from_pages(ordered_pages)
    if not markers:
        return []

    page_lines = [normalize_outline_page_lines(page.normalized_text) for page in ordered_pages]
    scopes: list[ProcessingScope] = []
    document_id = str(document_asset.document_id)

    for index, marker in enumerate(markers):
        if _has_outline_child(markers, index):
            continue

        next_marker = markers[index + 1] if index + 1 < len(markers) else None
        page_chunks: list[tuple[str, str]] = []
        included_pages: list[int] = []

        for page_index in range(marker.page_index, len(ordered_pages)):
            lines = page_lines[page_index]
            if not lines:
                continue

            start_line = marker.line_index if page_index == marker.page_index else 0
            end_line = None
            if next_marker is not None and page_index == next_marker.page_index:
                end_line = next_marker.line_index
            if next_marker is not None and page_index > next_marker.page_index:
                break

            chunk_lines = lines[start_line:end_line]
            chunk_text = "\n".join(chunk_lines).strip()
            if chunk_text:
                page = ordered_pages[page_index]
                page_chunks.append((page.source_ref, chunk_text))
                if isinstance(page.page_number, int):
                    included_pages.append(page.page_number)

            if next_marker is not None and page_index == next_marker.page_index:
                break

        if not page_chunks:
            continue

        scope = ProcessingScope(
            scope_type="normative",
            chapter_label=marker.line_text,
            text="\n\n".join(text for _source_ref, text in page_chunks),
            page_start=min(included_pages) if included_pages else 0,
            page_end=max(included_pages) if included_pages else 0,
            section_ids=[],
        )
        scopes.append(_apply_page_scope_metadata(scope, document_id=document_id, page_chunks=page_chunks))

    return scopes


def _build_commentary_scopes(document_asset: DocumentAsset) -> list[ProcessingScope]:
    _normative_pages, ordered_pages = _partition_pages(document_asset)
    commentary_pages: list[PageWindow] = []

    for page in ordered_pages:
        lines = normalize_outline_page_lines(page.normalized_text)
        lines = _strip_commentary_appendix_heading(lines)
        if not lines:
            continue
        page_text = "\n".join(lines).strip()
        if not page_text:
            continue
        commentary_pages.append(
            PageWindow(
                page_start=page.page_number or 0,
                page_end=page.page_number or 0,
                section_ids=[],
                text=page_text,
            )
        )

    if not commentary_pages:
        return []

    commentary_text = "\n\n".join(page.text for page in commentary_pages if page.text.strip())
    if not commentary_text.strip():
        return []

    commentary_scopes = _split_by_chapters(
        commentary_text,
        commentary_pages[0].page_start,
        commentary_pages[-1].page_end,
        [],
        "commentary",
    )
    document_id = str(document_asset.document_id)
    commentary_nodes = [
        StructuralNode(
            node_type="page",
            source_ref=page.source_ref,
            text="\n".join(normalize_outline_page_lines(page.normalized_text)),
            page_start=page.page_number or 0,
            page_end=page.page_number or 0,
            section_ids=[],
        )
        for page in ordered_pages
    ]

    for scope in commentary_scopes:
        scope_nodes = _source_refs_for_scope(scope, commentary_nodes)
        page_chunks = [(node.source_ref, node.text) for node in scope_nodes if node.text]
        if not page_chunks:
            continue
        _apply_page_scope_metadata(scope, document_id=document_id, page_chunks=page_chunks)

    return commentary_scopes


def build_processing_scopes(document_asset: DocumentAsset) -> list[ProcessingScope]:
    nodes = build_structural_nodes(document_asset)
    page_nodes = [node for node in nodes if node.node_type == "page"]
    table_nodes = [node for node in nodes if node.node_type == "table"]

    scopes: list[ProcessingScope] = []
    outline_scopes = _build_outline_leaf_scopes(document_asset)
    if outline_scopes:
        scopes.extend(outline_scopes)
        scopes.extend(_build_commentary_scopes(document_asset))
    elif page_nodes:
        windows = [
            PageWindow(
                page_start=node.page_start,
                page_end=node.page_end,
                section_ids=node.section_ids,
                text=node.text,
            )
            for node in page_nodes
        ]
        scopes.extend(split_into_scopes(windows))

        for scope in scopes:
            scope_nodes = _source_refs_for_scope(scope, page_nodes)
            if scope_nodes:
                scope.page_start = min(node.page_start for node in scope_nodes)
                scope.page_end = max(node.page_end for node in scope_nodes)
            scope_refs = _dedupe_in_order([node.source_ref for node in scope_nodes])
            scope.source_refs = scope_refs
            scope.context = {
                "document_id": str(document_asset.document_id),
                "source_refs": scope_refs,
                "node_types": [node.node_type for node in scope_nodes],
            }
            scope.source_chunks = [
                {
                    "text": node.text,
                    "source_ref": node.source_ref,
                    "node_type": node.node_type,
                }
                for node in scope_nodes
            ]

    for node in table_nodes:
        table_title = node.table_title or "未命名表格"
        scopes.append(
            ProcessingScope(
                scope_type="table",
                chapter_label=f"表格: {table_title}",
                text=node.text,
                page_start=node.page_start,
                page_end=node.page_end,
                section_ids=node.section_ids,
                source_refs=[node.source_ref],
                context={
                    "document_id": str(document_asset.document_id),
                    "source_ref": node.source_ref,
                    "node_type": "table",
                    "table_title": table_title,
                },
            )
        )

    return sorted(
        scopes,
        key=lambda scope: (
            scope.page_start,
            1 if scope.scope_type == "table" else 0,
            scope.chapter_label,
        ),
    )
