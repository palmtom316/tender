"""Build structural nodes and processing scopes from parse assets."""

from __future__ import annotations

from dataclasses import dataclass

from tender_backend.services.norm_service.document_assets import DocumentAsset
from tender_backend.services.norm_service.layout_compressor import PageWindow
from tender_backend.services.norm_service.scope_splitter import ProcessingScope, split_into_scopes


@dataclass(frozen=True)
class StructuralNode:
    node_type: str  # "page" | "table"
    source_ref: str
    text: str
    page_start: int
    page_end: int
    section_ids: list[str]
    table_title: str | None = None


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

    for page in document_asset.pages:
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
            )
        )

    for table in document_asset.tables:
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
            )
        )

    return sorted(nodes, key=lambda n: (n.page_start, 1 if n.node_type == "table" else 0, n.source_ref))


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


def build_processing_scopes(document_asset: DocumentAsset) -> list[ProcessingScope]:
    nodes = build_structural_nodes(document_asset)
    page_nodes = [node for node in nodes if node.node_type == "page"]
    table_nodes = [node for node in nodes if node.node_type == "table"]

    scopes: list[ProcessingScope] = []
    if page_nodes:
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
