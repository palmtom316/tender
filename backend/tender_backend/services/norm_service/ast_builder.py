"""Build clause AST from extracted entries."""

from __future__ import annotations

import hashlib
import re
from uuid import UUID, uuid4

import structlog

from .ast_models import ClauseASTNode

logger = structlog.stdlib.get_logger(__name__)

_CLAUSE_NO_STRIP = re.compile(r"^[第]?\s*|[条款]$")
_CLAUSE_NO_NORMALIZE = re.compile(r"^(\d+(?:[.\-]\d+)*)")
_EMBEDDED_CLAUSE_LEAD = re.compile(r"^(?P<clause_no>\d+(?:\.\d+)+)\s+(?P<body>\S.*)$", re.S)
_CLAUSE_LABEL_RE = re.compile(r"^\s*(?:[A-Z]\.)?\d+(?:\.\d+)+\s*$")
_ITEM_MARKER_RE = re.compile(r"^\s*(?:[（(]\s*(\d+)\s*[）)]|(\d+)([、.)）]?))\s*$")
_LEADING_SEQUENCE_TEXT_RE = re.compile(
    r"^\s*(?:[（(]\s*(?P<bracketed>\d+)\s*[）)]|(?P<plain>\d+)(?P<suffix>[、.)）]?))\s*(?P<body>\S.*)$",
    re.S,
)
_ALLOWED_CLAUSE_TYPES = {"normative", "commentary"}
_ALLOWED_SOURCE_TYPES = {"text", "table"}
_ALLOWED_NODE_TYPES = {"clause", "commentary", "item", "subitem"}


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


def _nearest_parent_id(
    clause_no: str,
    *,
    clause_type: str,
    clause_id_map: dict[str, UUID],
) -> UUID | None:
    parent_no = _parent_no(clause_no)
    while parent_no:
        parent_id = clause_id_map.get(f"{clause_type}:{parent_no}")
        if parent_id is not None:
            return parent_id
        parent_no = _parent_no(parent_no)
    return None


def deduplicate_entries(entries: list[dict]) -> list[dict]:
    """Remove duplicate entries based on node identity, keeping first occurrence."""
    seen: set[str] = set()
    result: list[dict] = []
    for sibling_index, entry in enumerate(entries):
        ctype = _normalize_clause_type(entry.get("clause_type", "normative"))
        node_type = str(entry.get("node_type") or "").strip()
        if node_type not in _ALLOWED_NODE_TYPES:
            node_type = "commentary" if ctype == "commentary" else "clause"
        node_key = entry.get("node_key")
        if not node_key:
            raw_label = entry.get("node_label")
            node_label = raw_label.strip().replace("）", ")") if isinstance(raw_label, str) else None
            node_key = _build_node_key(
                clause_type=ctype,
                node_type=node_type,
                clause_no=str(entry.get("clause_no") or ""),
                node_label=node_label,
                parent_key=None,
                sibling_index=sibling_index,
                source_label=entry.get("source_label"),
            )
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
    return label.replace("（", "(").replace("）", ")")


def _normalize_item_marker(raw: object) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    match = _ITEM_MARKER_RE.match(text)
    if not match:
        return None
    bracketed = match.group(1)
    plain = match.group(2)
    suffix = match.group(3) or ""
    if bracketed:
        return f"({bracketed})"
    if suffix in {")", ")", "）"}:
        return f"{plain})"
    if suffix == "、":
        return f"{plain}、"
    return plain


def _extract_clause_no_from_node_label(raw: object) -> str | None:
    label = _normalize_node_label(str(raw) if raw is not None else None)
    if not label or not _CLAUSE_LABEL_RE.match(label):
        return None
    normalized = normalize_clause_no(label)
    if not normalized:
        return None
    return normalized


def _leading_sequence_parts(text: object) -> tuple[str, str] | None:
    match = _LEADING_SEQUENCE_TEXT_RE.match(str(text or "").strip())
    if not match:
        return None
    bracketed = match.group("bracketed")
    plain = match.group("plain")
    suffix = match.group("suffix") or ""
    body = str(match.group("body") or "").strip()
    if not body:
        return None
    if bracketed:
        label = f"({bracketed})"
    elif suffix in {")", "）"}:
        label = f"{plain})"
    elif suffix == "、":
        label = f"{plain}、"
    else:
        label = str(plain or "").strip()
    if not label:
        return None
    return label, body


def _entry_invites_list_children(entry: dict) -> bool:
    text_parts = [
        str(entry.get("clause_title") or "").strip(),
        str(entry.get("clause_text") or "").strip(),
    ]
    combined = "\n".join(part for part in text_parts if part).strip()
    if not combined:
        return False
    return combined.endswith(("：", ":")) or "下列" in combined or "如下" in combined


def _sequence_node_type(raw_label: str | None, existing_type: str | None = None) -> str:
    if existing_type in {"item", "subitem"}:
        return existing_type
    if raw_label and raw_label.endswith(")"):
        return "item"
    return "item"


def _nested_sequence_node_type(node_type: str, *, parent_node_type: str | None) -> str:
    if parent_node_type in {"item", "subitem"} and node_type == "item":
        return "subitem"
    return node_type


def _repair_flat_sequence_entries(entries: list[dict]) -> list[dict]:
    repaired: list[dict] = []
    active_parent_clause_no: str | None = None
    latest_clause_no: str | None = None
    next_item_index = 1

    for entry in entries:
        current = dict(entry)
        current = _reclassify_same_clause_sequence_entry(current, inherited_clause_no=active_parent_clause_no)
        raw_clause_no = current.get("clause_no")
        item_label = _normalize_item_marker(raw_clause_no)
        node_type = str(current.get("node_type") or "").strip() or None
        normalized_clause_no = normalize_clause_no(raw_clause_no) if raw_clause_no else ""
        has_real_clause_no = bool(normalized_clause_no and not item_label)
        clause_label_no = (
            _extract_clause_no_from_node_label(current.get("node_label"))
            if not str(raw_clause_no or "").strip() and node_type in {"item", "subitem"}
            else None
        )

        if has_real_clause_no:
            current["clause_no"] = normalized_clause_no
            repaired.append(current)
            latest_clause_no = normalized_clause_no
            if _entry_invites_list_children(current):
                active_parent_clause_no = normalized_clause_no
                next_item_index = 1
            else:
                active_parent_clause_no = None
            continue

        if clause_label_no:
            current["clause_no"] = clause_label_no
            current["node_type"] = "clause"
            current["node_label"] = None
            repaired.append(current)
            latest_clause_no = clause_label_no
            if _entry_invites_list_children(current):
                active_parent_clause_no = clause_label_no
                next_item_index = 1
            else:
                active_parent_clause_no = None
            continue

        if str(current.get("source_type") or "").strip() == "table" and not str(raw_clause_no or "").strip():
            repaired.append(current)
            active_parent_clause_no = None
            continue

        if active_parent_clause_no and (item_label or not str(raw_clause_no or "").strip()):
            current["node_type"] = _sequence_node_type(item_label, node_type)
            current["node_label"] = _normalize_node_label(current.get("node_label")) or item_label or str(next_item_index)
            current["clause_no"] = active_parent_clause_no
            repaired.append(current)
            next_item_index += 1
            continue

        if latest_clause_no and node_type in {"item", "subitem"} and not str(raw_clause_no or "").strip():
            current["clause_no"] = latest_clause_no
            current["node_label"] = _normalize_node_label(current.get("node_label")) or str(next_item_index)
            repaired.append(current)
            if node_type == "item":
                next_item_index += 1
            continue

        if normalized_clause_no:
            current["clause_no"] = normalized_clause_no
        repaired.append(current)
        active_parent_clause_no = None

    return repaired


def _normalize_clause_type(raw: object) -> str:
    value = str(raw or "").strip()
    if value in _ALLOWED_CLAUSE_TYPES:
        return value
    return "normative"


def _normalize_source_type(raw: object) -> str:
    value = str(raw or "").strip()
    if value in _ALLOWED_SOURCE_TYPES:
        return value
    return "text"


def _default_node_type(entry: dict, *, clause_type: str) -> str:
    raw_value = str(entry.get("node_type") or "").strip()
    if raw_value in _ALLOWED_NODE_TYPES:
        return raw_value
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


def _source_label_fingerprint(source_label: object) -> str:
    text = str(source_label or "").strip()
    if not text:
        return ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _build_node_key(
    *,
    clause_type: str,
    node_type: str,
    clause_no: str,
    node_label: str | None,
    parent_key: str | None,
    sibling_index: int,
    source_label: object = None,
) -> str:
    fingerprint = _source_label_fingerprint(source_label)
    suffix = f"@{fingerprint}" if fingerprint else ""

    if node_type == "clause" and clause_no:
        return f"{clause_no}{suffix}"
    if parent_key and node_label:
        return f"{parent_key}#{node_label}"
    if clause_no and node_label:
        return f"{clause_no}#{node_label}{suffix}"
    if parent_key:
        return f"{parent_key}#{node_type}{sibling_index + 1}"
    if node_type == "commentary" and clause_no:
        return f"{clause_no}#commentary{suffix}"
    if clause_no:
        return f"{clause_no}{suffix}"
    if node_label:
        return f"{clause_type}:{node_type}:{node_label}{suffix}"
    return f"{clause_type}:{node_type}:{sibling_index + 1}{suffix}"


def _promote_embedded_clause_child(entry: dict, *, inherited_clause_no: str | None) -> dict:
    promoted = dict(entry)
    node_type = promoted.get("node_type")
    if node_type not in {"item", "subitem"}:
        return promoted

    clause_text = str(promoted.get("clause_text") or "").strip()
    if not clause_text:
        return promoted

    match = _EMBEDDED_CLAUSE_LEAD.match(clause_text)
    if not match:
        return promoted

    clause_no = normalize_clause_no(match.group("clause_no"))
    if not clause_no:
        return promoted

    inherited = inherited_clause_no or ""
    if inherited and clause_no != inherited and not clause_no.startswith(f"{inherited}."):
        return promoted

    body = match.group("body").strip()
    if not body:
        return promoted

    title_line, separator, remainder = body.partition("\n")
    promoted["node_type"] = "clause"
    promoted["node_label"] = None
    promoted["clause_no"] = clause_no
    if separator and remainder.strip():
        promoted["clause_title"] = title_line.strip() or promoted.get("clause_title")
        promoted["clause_text"] = remainder.strip()
    else:
        promoted["clause_text"] = body
    return promoted


def _promote_clause_label_child(entry: dict, *, inherited_clause_no: str | None) -> dict:
    promoted = dict(entry)
    node_type = promoted.get("node_type")
    if node_type not in {"item", "subitem"}:
        return promoted
    if str(promoted.get("clause_no") or "").strip():
        return promoted

    clause_no = _extract_clause_no_from_node_label(promoted.get("node_label"))
    if not clause_no:
        return promoted

    inherited = inherited_clause_no or ""
    if inherited and clause_no != inherited and not clause_no.startswith(f"{inherited}."):
        return promoted

    promoted["node_type"] = "clause"
    promoted["clause_no"] = clause_no
    promoted["node_label"] = None
    return promoted


def _promote_implicit_sequence_child(entry: dict, *, inherited_clause_no: str | None) -> dict:
    promoted = dict(entry)
    if not inherited_clause_no:
        return promoted
    if str(promoted.get("source_type") or "").strip() == "table":
        return promoted
    if str(promoted.get("clause_no") or "").strip():
        return promoted
    if str(promoted.get("node_label") or "").strip():
        return promoted

    node_type = str(promoted.get("node_type") or "").strip()
    if node_type in {"item", "subitem", "commentary"}:
        return promoted

    parts = _leading_sequence_parts(promoted.get("clause_text"))
    if not parts:
        return promoted

    label, body = parts
    promoted["node_type"] = "item"
    promoted["node_label"] = label
    promoted["clause_no"] = inherited_clause_no
    promoted["clause_text"] = body
    return promoted


def _reclassify_same_clause_sequence_entry(entry: dict, *, inherited_clause_no: str | None) -> dict:
    promoted = dict(entry)
    if not inherited_clause_no:
        return promoted
    if str(promoted.get("source_type") or "").strip() == "table":
        return promoted
    if str(promoted.get("node_label") or "").strip():
        return promoted

    node_type = str(promoted.get("node_type") or "").strip()
    if node_type in {"item", "subitem", "commentary"}:
        return promoted

    clause_no = normalize_clause_no(promoted.get("clause_no")) if promoted.get("clause_no") else ""
    if clause_no != inherited_clause_no:
        return promoted

    parts = _leading_sequence_parts(promoted.get("clause_text"))
    if not parts:
        return promoted

    label, body = parts
    promoted["node_type"] = "item"
    promoted["node_label"] = label
    promoted["clause_no"] = inherited_clause_no
    promoted["clause_text"] = body
    return promoted


def _build_nested_ast(
    entries: list[dict],
    *,
    standard_id: UUID,
    parent_id: UUID | None = None,
    parent_key: str | None = None,
    parent_node_type: str | None = None,
    inherited_clause_no: str | None = None,
    clause_id_map: dict[str, UUID] | None = None,
    seen_node_keys: set[str] | None = None,
) -> list[ClauseASTNode]:
    nodes: list[ClauseASTNode] = []
    clause_id_map = clause_id_map if clause_id_map is not None else {}
    seen_node_keys = seen_node_keys if seen_node_keys is not None else set()

    for sibling_index, entry in enumerate(entries):
        current_entry = _promote_embedded_clause_child(entry, inherited_clause_no=inherited_clause_no)
        current_entry = _promote_clause_label_child(current_entry, inherited_clause_no=inherited_clause_no)
        current_entry = _promote_implicit_sequence_child(current_entry, inherited_clause_no=inherited_clause_no)
        current_entry = _reclassify_same_clause_sequence_entry(current_entry, inherited_clause_no=inherited_clause_no)
        clause_type = _normalize_clause_type(entry.get("clause_type", "normative"))
        node_type = _default_node_type(current_entry, clause_type=clause_type)
        item_marker = _normalize_item_marker(current_entry.get("clause_no"))
        if inherited_clause_no and item_marker:
            current_entry["node_type"] = _sequence_node_type(item_marker, node_type)
            current_entry["node_label"] = _normalize_node_label(current_entry.get("node_label")) or item_marker
            current_entry["clause_no"] = inherited_clause_no
            node_type = current_entry["node_type"]
        node_type = _nested_sequence_node_type(node_type, parent_node_type=parent_node_type)
        current_entry["node_type"] = node_type
        raw_clause_no = current_entry.get("clause_no")
        clause_no = normalize_clause_no(raw_clause_no) if raw_clause_no else (inherited_clause_no or "")
        node_label = _normalize_node_label(current_entry.get("node_label"))
        node_key = current_entry.get("node_key") or _build_node_key(
            clause_type=clause_type,
            node_type=node_type,
            clause_no=clause_no,
            node_label=node_label,
            parent_key=parent_key,
            sibling_index=sibling_index,
            source_label=current_entry.get("source_label"),
        )
        dedupe_key = f"{clause_type}:{node_key}" if node_key else ""
        if dedupe_key and dedupe_key in seen_node_keys:
            logger.debug("duplicate_clause_removed", node_key=node_key, clause_type=clause_type)
            continue
        if dedupe_key:
            seen_node_keys.add(dedupe_key)
        node_id = uuid4()
        resolved_parent_id = parent_id
        if resolved_parent_id is None and node_type == "clause" and clause_no:
            resolved_parent_id = _nearest_parent_id(
                clause_no,
                clause_type=clause_type,
                clause_id_map=clause_id_map,
            )
        elif resolved_parent_id is None and node_type in {"item", "subitem"} and clause_no:
            resolved_parent_id = clause_id_map.get(f"{clause_type}:{clause_no}")
            if resolved_parent_id is None:
                resolved_parent_id = _nearest_parent_id(
                    clause_no,
                    clause_type=clause_type,
                    clause_id_map=clause_id_map,
                )

        node = ClauseASTNode(
            id=node_id,
            standard_id=standard_id,
            parent_id=resolved_parent_id,
            clause_no=clause_no or None,
            node_type=node_type,
            node_key=node_key,
            node_label=node_label,
            clause_title=(current_entry.get("clause_title") or "").strip() or None,
            clause_text=(current_entry.get("clause_text") or "").strip(),
            summary=(current_entry.get("summary") or "").strip() or None,
            tags=_normalize_tags(current_entry.get("tags")),
            page_start=current_entry.get("page_start"),
            page_end=current_entry.get("page_end"),
            clause_type=clause_type,
            source_type=_normalize_source_type(current_entry.get("source_type", "text")),
            source_label=current_entry.get("source_label"),
            source_ref=current_entry.get("source_ref"),
            source_refs=_normalize_source_refs(current_entry.get("source_refs")),
        )
        if node_type == "clause" and clause_no:
            clause_id_map[f"{clause_type}:{clause_no}"] = node_id

        children = current_entry.get("children")
        if isinstance(children, list) and children:
            node.children = _build_nested_ast(
                children,
                standard_id=standard_id,
                parent_id=node_id,
                parent_key=node_key,
                parent_node_type=node_type,
                inherited_clause_no=clause_no or inherited_clause_no,
                clause_id_map=clause_id_map,
                seen_node_keys=seen_node_keys,
            )

        nodes.append(node)

    return nodes


def _build_flat_ast(entries: list[dict], *, standard_id: UUID) -> list[ClauseASTNode]:
    normalized_entries: list[dict] = []
    for entry in _repair_flat_sequence_entries(entries):
        current = dict(entry)
        current["clause_no"] = normalize_clause_no(current.get("clause_no"))
        normalized_entries.append(current)

    deduped = deduplicate_entries(normalized_entries)
    clause_id_map: dict[str, UUID] = {}
    prepared: list[tuple[dict, UUID, str, str, str | None, str]] = []

    for sibling_index, entry in enumerate(deduped):
        clause_type = _normalize_clause_type(entry.get("clause_type", "normative"))
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
            source_label=entry.get("source_label"),
        )
        node_id = uuid4()
        key = f"{clause_type}:{node_key}" if node_key else ""
        if key:
            clause_id_map[key] = node_id
        # Also register under the canonical (unsuffixed) clause key so parent
        # lookups via clause_no still find the first clause for each number.
        if node_type == "clause" and clause_no:
            canonical_key = f"{clause_type}:{clause_no}"
            clause_id_map.setdefault(canonical_key, node_id)
        prepared.append((entry, node_id, clause_type, node_type, node_label, node_key))

    all_nodes: list[ClauseASTNode] = []
    id_to_node: dict[UUID, ClauseASTNode] = {}
    latest_clause_id_by_clause_no: dict[str, UUID] = {}
    latest_item_id_by_clause_no: dict[str, UUID] = {}

    for entry, node_id, clause_type, node_type, node_label, node_key in prepared:
        clause_no = entry.get("clause_no") or ""
        parent_id = None
        if node_type == "clause" and clause_no:
            parent_id = _nearest_parent_id(
                clause_no,
                clause_type=clause_type,
                clause_id_map=clause_id_map,
            )
        elif node_type == "item" and clause_no:
            parent_id = latest_clause_id_by_clause_no.get(clause_no)
            if parent_id is None:
                parent_id = _nearest_parent_id(
                    clause_no,
                    clause_type=clause_type,
                    clause_id_map=clause_id_map,
                )
        elif node_type == "subitem" and clause_no:
            parent_id = latest_item_id_by_clause_no.get(clause_no) or latest_clause_id_by_clause_no.get(clause_no)
            if parent_id is None:
                parent_id = _nearest_parent_id(
                    clause_no,
                    clause_type=clause_type,
                    clause_id_map=clause_id_map,
                )

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
            source_type=_normalize_source_type(entry.get("source_type", "text")),
            source_label=entry.get("source_label"),
            source_ref=entry.get("source_ref"),
            source_refs=_normalize_source_refs(entry.get("source_refs")),
        )
        all_nodes.append(node)
        id_to_node[node.id] = node
        if clause_no and node_type == "clause":
            latest_clause_id_by_clause_no[clause_no] = node_id
            latest_item_id_by_clause_no[clause_no] = None
        elif clause_no and node_type == "item":
            latest_item_id_by_clause_no[clause_no] = node_id

    roots: list[ClauseASTNode] = []
    for node in all_nodes:
        if node.parent_id and node.parent_id in id_to_node:
            id_to_node[node.parent_id].children.append(node)
        else:
            roots.append(node)

    return roots


def _iter_ast_nodes(nodes: list[ClauseASTNode]) -> list[ClauseASTNode]:
    result: list[ClauseASTNode] = []
    stack = list(nodes)
    while stack:
        node = stack.pop(0)
        result.append(node)
        if node.children:
            stack[0:0] = node.children
    return result


def _attach_clause_hierarchy(roots: list[ClauseASTNode]) -> list[ClauseASTNode]:
    all_nodes = _iter_ast_nodes(roots)
    node_by_id = {node.id: node for node in all_nodes}
    clause_by_key = {
        f"{node.clause_type}:{node.clause_no}": node
        for node in all_nodes
        if node.node_type == "clause" and node.clause_no
    }
    root_ids = {node.id for node in roots}

    for node in all_nodes:
        if not node.parent_id:
            continue
        parent = node_by_id.get(node.parent_id)
        if parent is None or parent.id == node.id:
            continue
        if any(child.id == node.id for child in parent.children):
            continue
        parent.children.append(node)

    for node in all_nodes:
        if node.node_type != "clause" or not node.clause_no:
            continue

        parent_id = node.parent_id
        if parent_id is None:
            parent_id = _nearest_parent_id(
                node.clause_no,
                clause_type=node.clause_type,
                clause_id_map={key: value.id for key, value in clause_by_key.items()},
            )
        if parent_id is not None:
            parent = node_by_id.get(parent_id)
            if parent is None or parent.id == node.id:
                continue
            node.parent_id = parent_id
            if any(child.id == node.id for child in parent.children):
                continue
            parent.children.append(node)

    return [node for node in roots if node.id in root_ids and node.parent_id is None]


def build_clause_ast(entries: list[dict], standard_id: UUID) -> list[ClauseASTNode]:
    """Build clause AST roots from extracted entries."""
    if not entries:
        return []

    repaired_entries = _repair_flat_sequence_entries(entries)
    has_explicit_children = any(
        isinstance(entry.get("children"), list) and entry.get("children")
        for entry in repaired_entries
    )
    if has_explicit_children:
        roots = _build_nested_ast(repaired_entries, standard_id=standard_id)
        return _attach_clause_hierarchy(roots)
    return _build_flat_ast(repaired_entries, standard_id=standard_id)
