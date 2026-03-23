"""Build clause AST from extracted entries."""

from __future__ import annotations

import re
from uuid import UUID, uuid4

import structlog

from .ast_models import ClauseASTNode

logger = structlog.stdlib.get_logger(__name__)

_CLAUSE_NO_STRIP = re.compile(r"^[第]?\s*|[条款]$")
_CLAUSE_NO_NORMALIZE = re.compile(r"^(\d+(?:[.\-]\d+)*)")


def normalize_clause_no(raw: str | None) -> str:
    """Normalize clause number to dot-separated form (e.g. '3.2.1')."""
    if not raw:
        return ""
    cleaned = _CLAUSE_NO_STRIP.sub("", raw.strip())
    cleaned = cleaned.replace("\u3002", ".").replace("\uff0e", ".")
    m = _CLAUSE_NO_NORMALIZE.match(cleaned)
    return m.group(1) if m else cleaned


def _parent_no(clause_no: str) -> str:
    parts = clause_no.split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else ""


def deduplicate_entries(entries: list[dict]) -> list[dict]:
    """Remove duplicate entries based on node identity, keeping first occurrence."""
    seen: set[str] = set()
    result: list[dict] = []
    for entry in entries:
        ctype = entry.get("clause_type", "normative")
        node_type = entry.get("node_type") or ("commentary" if ctype == "commentary" else "clause")
        node_key = entry.get("node_key")
        if not node_key:
            cno = entry.get("clause_no", "")
            if node_type == "commentary" and cno:
                node_key = f"{cno}#commentary"
            else:
                node_key = cno
        key = f"{ctype}:{node_key}" if node_key else ""
        if key and key in seen:
            logger.debug("duplicate_clause_removed", node_key=node_key, clause_type=ctype)
            continue
        if key:
            seen.add(key)
        result.append(entry)
    return result


def _normalize_node_label(raw: str | None) -> str | None:
    if raw is None:
        return None
    label = raw.strip()
    if not label:
        return None
    return label.replace("）", ")")


def _default_node_type(entry: dict, *, clause_type: str) -> str:
    if entry.get("node_type"):
        return str(entry["node_type"]).strip()
    if clause_type == "commentary":
        return "commentary"
    return "clause"


def _normalize_tags(raw: object) -> list[str]:
    tags = raw or []
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, list):
        return [str(t).strip() for t in tags if str(t).strip()]
    return []


def _normalize_source_refs(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        value = raw.strip()
        return [value] if value else []
    if isinstance(raw, list):
        refs: list[str] = []
        for item in raw:
            value = str(item).strip()
            if value:
                refs.append(value)
        return refs
    value = str(raw).strip()
    return [value] if value else []


def _build_node_key(
    *,
    clause_type: str,
    node_type: str,
    clause_no: str,
    node_label: str | None,
    parent_key: str | None,
    sibling_index: int,
) -> str:
    if parent_key and node_label:
        return f"{parent_key}#{node_label}"
    if parent_key:
        return f"{parent_key}#{node_type}{sibling_index + 1}"
    if node_type == "commentary" and clause_no:
        return f"{clause_no}#commentary"
    if clause_no:
        return clause_no
    if node_label:
        return f"{clause_type}:{node_type}:{node_label}"
    return f"{clause_type}:{node_type}:{sibling_index + 1}"


def _build_nested_ast(
    entries: list[dict],
    *,
    standard_id: UUID,
    parent_id: UUID | None = None,
    parent_key: str | None = None,
    inherited_clause_no: str | None = None,
) -> list[ClauseASTNode]:
    nodes: list[ClauseASTNode] = []
    seen_node_keys: set[str] = set()

    for sibling_index, entry in enumerate(entries):
        clause_type = str(entry.get("clause_type", "normative")).strip() or "normative"
        node_type = _default_node_type(entry, clause_type=clause_type)
        raw_clause_no = entry.get("clause_no")
        clause_no = normalize_clause_no(raw_clause_no) if raw_clause_no else (inherited_clause_no or "")
        node_label = _normalize_node_label(entry.get("node_label"))
        node_key = entry.get("node_key") or _build_node_key(
            clause_type=clause_type,
            node_type=node_type,
            clause_no=clause_no,
            node_label=node_label,
            parent_key=parent_key,
            sibling_index=sibling_index,
        )
        dedupe_key = f"{clause_type}:{node_key}" if node_key else ""
        if dedupe_key and dedupe_key in seen_node_keys:
            logger.debug("duplicate_clause_removed", node_key=node_key, clause_type=clause_type)
            continue
        if dedupe_key:
            seen_node_keys.add(dedupe_key)
        node_id = uuid4()

        node = ClauseASTNode(
            id=node_id,
            standard_id=standard_id,
            parent_id=parent_id,
            clause_no=clause_no or None,
            node_type=node_type,
            node_key=node_key,
            node_label=node_label,
            clause_title=(entry.get("clause_title") or "").strip() or None,
            clause_text=(entry.get("clause_text") or "").strip(),
            summary=(entry.get("summary") or "").strip() or None,
            tags=_normalize_tags(entry.get("tags")),
            page_start=entry.get("page_start"),
            page_end=entry.get("page_end"),
            clause_type=clause_type,
            source_type=entry.get("source_type", "text"),
            source_label=entry.get("source_label"),
            source_ref=entry.get("source_ref"),
            source_refs=_normalize_source_refs(entry.get("source_refs")),
        )

        children = entry.get("children")
        if isinstance(children, list) and children:
            node.children = _build_nested_ast(
                deduplicate_entries(children),
                standard_id=standard_id,
                parent_id=node_id,
                parent_key=node_key,
                inherited_clause_no=clause_no or inherited_clause_no,
            )

        nodes.append(node)

    return nodes


def _build_flat_ast(entries: list[dict], *, standard_id: UUID) -> list[ClauseASTNode]:
    normalized_entries: list[dict] = []
    for entry in entries:
        current = dict(entry)
        current["clause_no"] = normalize_clause_no(current.get("clause_no"))
        normalized_entries.append(current)

    deduped = deduplicate_entries(normalized_entries)
    clause_id_map: dict[str, UUID] = {}
    prepared: list[tuple[dict, UUID, str, str, str | None, str]] = []

    for sibling_index, entry in enumerate(deduped):
        clause_type = str(entry.get("clause_type", "normative")).strip() or "normative"
        node_type = _default_node_type(entry, clause_type=clause_type)
        clause_no = entry.get("clause_no") or ""
        node_label = _normalize_node_label(entry.get("node_label"))
        node_key = entry.get("node_key") or _build_node_key(
            clause_type=clause_type,
            node_type=node_type,
            clause_no=clause_no,
            node_label=node_label,
            parent_key=None,
            sibling_index=sibling_index,
        )
        node_id = uuid4()
        key = f"{clause_type}:{node_key}" if node_key else ""
        if key:
            clause_id_map[key] = node_id
        prepared.append((entry, node_id, clause_type, node_type, node_label, node_key))

    all_nodes: list[ClauseASTNode] = []
    id_to_node: dict[UUID, ClauseASTNode] = {}
    for entry, node_id, clause_type, node_type, node_label, node_key in prepared:
        clause_no = entry.get("clause_no") or ""
        parent_id = None
        if node_type == "clause" and clause_no:
            parent_no = _parent_no(clause_no)
            if parent_no:
                parent_id = clause_id_map.get(f"{clause_type}:{parent_no}")

        node = ClauseASTNode(
            id=node_id,
            standard_id=standard_id,
            parent_id=parent_id,
            clause_no=clause_no or None,
            node_type=node_type,
            node_key=node_key,
            node_label=node_label,
            clause_title=(entry.get("clause_title") or "").strip() or None,
            clause_text=(entry.get("clause_text") or "").strip(),
            summary=(entry.get("summary") or "").strip() or None,
            tags=_normalize_tags(entry.get("tags")),
            page_start=entry.get("page_start"),
            page_end=entry.get("page_end"),
            clause_type=clause_type,
            source_type=entry.get("source_type", "text"),
            source_label=entry.get("source_label"),
            source_ref=entry.get("source_ref"),
            source_refs=_normalize_source_refs(entry.get("source_refs")),
        )
        all_nodes.append(node)
        id_to_node[node.id] = node

    roots: list[ClauseASTNode] = []
    for node in all_nodes:
        if node.parent_id and node.parent_id in id_to_node:
            id_to_node[node.parent_id].children.append(node)
        else:
            roots.append(node)

    return roots


def build_clause_ast(entries: list[dict], standard_id: UUID) -> list[ClauseASTNode]:
    """Build clause AST roots from extracted entries."""
    if not entries:
        return []

    has_explicit_children = any(isinstance(entry.get("children"), list) and entry.get("children") for entry in entries)
    if has_explicit_children:
        return _build_nested_ast(deduplicate_entries(entries), standard_id=standard_id)
    return _build_flat_ast(entries, standard_id=standard_id)
