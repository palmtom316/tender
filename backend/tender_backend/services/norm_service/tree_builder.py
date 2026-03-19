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
    """Remove duplicate entries based on clause_no, keeping first occurrence."""
    seen: set[str] = set()
    result: list[dict] = []
    for entry in entries:
        cno = entry.get("clause_no", "")
        ctype = entry.get("clause_type", "normative")
        key = f"{ctype}:{cno}" if cno else ""
        if key and key in seen:
            logger.debug("duplicate_clause_removed", clause_no=cno, clause_type=ctype)
            continue
        if key:
            seen.add(key)
        result.append(entry)
    return result


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

    # Normalize and deduplicate
    for entry in entries:
        entry["clause_no"] = normalize_clause_no(entry.get("clause_no"))

    entries = deduplicate_entries(entries)

    # Build clause_no → UUID mapping for parent resolution
    clause_id_map: dict[str, UUID] = {}
    result: list[dict] = []

    # First pass: assign IDs
    for entry in entries:
        cid = uuid4()
        cno = entry["clause_no"]
        ctype = entry.get("clause_type", "normative")
        key = f"{ctype}:{cno}" if cno else ""
        if key:
            clause_id_map[key] = cid
        entry["_id"] = cid

    # Second pass: resolve parents and build output
    for i, entry in enumerate(entries):
        cno = entry["clause_no"]
        ctype = entry.get("clause_type", "normative")
        parent_id = None

        if cno:
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
            "clause_no": cno,
            "clause_title": (entry.get("clause_title") or "").strip() or None,
            "clause_text": (entry.get("clause_text") or "").strip(),
            "summary": (entry.get("summary") or "").strip() or None,
            "tags": tags,
            "page_start": entry.get("page_start"),
            "page_end": entry.get("page_end"),
            "sort_order": i,
            "clause_type": ctype,
        })

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
        if c["clause_type"] == "normative" and c["clause_no"]:
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
