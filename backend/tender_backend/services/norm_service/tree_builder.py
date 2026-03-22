"""Pure-Python clause tree builder.

Takes flat LLM-extracted entries and rebuilds a hierarchical clause tree
with deduplication, clause_no normalization, and validation.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

import structlog

logger = structlog.stdlib.get_logger(__name__)

# Pattern to normalize clause numbers: "第3.2.1条" → "3.2.1"
_CLAUSE_NO_STRIP = re.compile(r"^[第]?\s*|[条款]$")
_CLAUSE_NO_NORMALIZE = re.compile(r"^(\d+(?:[.\-]\d+)*)")


def normalize_clause_no(raw: str | None) -> str:
    """Normalize clause number to dot-separated form (e.g. '3.2.1')."""
    if not raw:
        return ""
    cleaned = _CLAUSE_NO_STRIP.sub("", raw.strip())
    # Replace Chinese period with dot
    cleaned = cleaned.replace("\u3002", ".").replace("\uff0e", ".")
    m = _CLAUSE_NO_NORMALIZE.match(cleaned)
    return m.group(1) if m else cleaned


def _clause_depth(clause_no: str) -> int:
    """Return nesting depth: '3' → 1, '3.2' → 2, '3.2.1' → 3."""
    if not clause_no:
        return 0
    return len(clause_no.split("."))


def _parent_no(clause_no: str) -> str:
    """Return parent clause number: '3.2.1' → '3.2', '3' → ''."""
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


def _flatten_entries(
    entries: list[dict],
    *,
    standard_id: UUID,
    parent_id: UUID | None = None,
    parent_key: str | None = None,
    inherited_clause_no: str | None = None,
) -> list[dict]:
    flattened: list[dict] = []

    for sibling_index, entry in enumerate(entries):
        clause_type = str(entry.get("clause_type", "normative")).strip() or "normative"
        node_type = _default_node_type(entry, clause_type=clause_type)
        raw_clause_no = entry.get("clause_no")
        clause_no = normalize_clause_no(raw_clause_no) if raw_clause_no else (inherited_clause_no or "")
        node_label = _normalize_node_label(entry.get("node_label"))
        node_key = _build_node_key(
            clause_type=clause_type,
            node_type=node_type,
            clause_no=clause_no,
            node_label=node_label,
            parent_key=parent_key,
            sibling_index=sibling_index,
        )
        node_id = uuid4()

        tags = entry.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        flattened.append({
            "id": node_id,
            "standard_id": standard_id,
            "parent_id": parent_id,
            "clause_no": clause_no or None,
            "node_type": node_type,
            "node_key": node_key,
            "node_label": node_label,
            "clause_title": (entry.get("clause_title") or "").strip() or None,
            "clause_text": (entry.get("clause_text") or "").strip(),
            "summary": (entry.get("summary") or "").strip() or None,
            "tags": tags,
            "page_start": entry.get("page_start"),
            "page_end": entry.get("page_end"),
            "clause_type": clause_type,
            "source_type": entry.get("source_type", "text"),
            "source_label": entry.get("source_label"),
        })

        children = entry.get("children")
        if isinstance(children, list) and children:
            flattened.extend(_flatten_entries(
                children,
                standard_id=standard_id,
                parent_id=node_id,
                parent_key=node_key,
                inherited_clause_no=clause_no or inherited_clause_no,
            ))

    return flattened


def build_tree(
    entries: list[dict],
    standard_id: UUID,
) -> list[dict]:
    """Build a hierarchical clause tree from flat entries.

    Each entry dict should have:
      clause_no, clause_title, clause_text, summary, tags,
      page_start, clause_type ('normative'|'commentary')

    Returns a flat list of clause dicts with id, parent_id, sort_order
    ready for bulk insertion.
    """
    if not entries:
        return []

    has_explicit_children = any(isinstance(entry.get("children"), list) and entry.get("children") for entry in entries)
    if has_explicit_children:
        result = deduplicate_entries(_flatten_entries(entries, standard_id=standard_id))
    else:
        # Normalize and deduplicate legacy flat entries first.
        for entry in entries:
            entry["clause_no"] = normalize_clause_no(entry.get("clause_no"))

        entries = deduplicate_entries(entries)

        clause_id_map: dict[str, UUID] = {}
        result = []

        for entry in entries:
            cid = uuid4()
            cno = entry["clause_no"]
            ctype = entry.get("clause_type", "normative")
            node_type = _default_node_type(entry, clause_type=ctype)
            node_key = _build_node_key(
                clause_type=ctype,
                node_type=node_type,
                clause_no=cno,
                node_label=_normalize_node_label(entry.get("node_label")),
                parent_key=None,
                sibling_index=len(result),
            )
            key = f"{ctype}:{node_key}" if node_key else ""
            if key:
                clause_id_map[key] = cid
            entry["_id"] = cid
            entry["_node_key"] = node_key
            entry["_node_type"] = node_type

        for entry in entries:
            cno = entry["clause_no"]
            ctype = entry.get("clause_type", "normative")
            node_type = entry["_node_type"]
            parent_id = None

            if node_type == "clause" and cno:
                pno = _parent_no(cno)
                if pno:
                    parent_key = f"{ctype}:{pno}"
                    parent_id = clause_id_map.get(parent_key)

            tags = entry.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            result.append({
                "id": entry["_id"],
                "standard_id": standard_id,
                "parent_id": parent_id,
                "clause_no": cno or None,
                "node_type": node_type,
                "node_key": entry["_node_key"],
                "node_label": _normalize_node_label(entry.get("node_label")),
                "clause_title": (entry.get("clause_title") or "").strip() or None,
                "clause_text": (entry.get("clause_text") or "").strip(),
                "summary": (entry.get("summary") or "").strip() or None,
                "tags": tags,
                "page_start": entry.get("page_start"),
                "page_end": entry.get("page_end"),
                "clause_type": ctype,
                "source_type": entry.get("source_type", "text"),
                "source_label": entry.get("source_label"),
            })

    for index, clause in enumerate(result):
        clause["sort_order"] = index

    logger.info(
        "tree_built",
        total_clauses=len(result),
        normative=sum(1 for r in result if r["clause_type"] == "normative"),
        commentary=sum(1 for r in result if r["clause_type"] == "commentary"),
    )
    return result


def link_commentary(clauses: list[dict]) -> list[dict]:
    """Link commentary clauses to their normative counterparts via commentary_clause_id.

    Modifies clauses in-place and returns them.
    """
    # Build normative clause_no → id map
    normative_map: dict[str, UUID] = {}
    for c in clauses:
        if c["clause_type"] == "normative" and c.get("node_type", "clause") == "clause" and c["clause_no"]:
            normative_map[c["clause_no"]] = c["id"]

    linked = 0
    for c in clauses:
        if c["clause_type"] == "commentary" and c["clause_no"]:
            norm_id = normative_map.get(c["clause_no"])
            if norm_id:
                c["commentary_clause_id"] = norm_id
                linked += 1
            else:
                c["commentary_clause_id"] = None
        else:
            c["commentary_clause_id"] = None

    logger.info("commentary_linked", total_commentary=linked)
    return clauses


def validate_tree(clauses: list[dict]) -> list[str]:
    """Validate the clause tree and return a list of warnings."""
    warnings: list[str] = []
    clause_ids = {c["id"] for c in clauses}
    parent_ids = {c["parent_id"] for c in clauses if c.get("parent_id")}

    for c in clauses:
        if c["parent_id"] and c["parent_id"] not in clause_ids:
            warnings.append(f"Clause {c['clause_no']}: parent_id references non-existent clause")
        if not c["clause_text"] and c["id"] not in parent_ids:
            warnings.append(f"Clause {c['clause_no']}: empty clause_text")

    if warnings:
        logger.warning("tree_validation_warnings", count=len(warnings), first=warnings[:3])

    return warnings
