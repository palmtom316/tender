"""Clause AST projection and compatibility tree builder surface.

`build_tree()` remains the public compatibility API for ingestion callers.
Internally it builds clause AST nodes and projects them into persistence-facing
flat dict rows with normalized page fields and preserved source metadata.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from .ast_builder import (
    build_clause_ast,
    deduplicate_entries as _deduplicate_entries,
    normalize_clause_no as _normalize_clause_no,
)
from .ast_models import ClauseASTNode

logger = structlog.stdlib.get_logger(__name__)


def normalize_clause_no(raw: str | None) -> str:
    """Backward-compatible export for clause number normalization."""
    return _normalize_clause_no(raw)


def deduplicate_entries(entries: list[dict]) -> list[dict]:
    """Backward-compatible export for entry deduplication."""
    return _deduplicate_entries(entries)


def _normalize_page_number(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return None
        if value.isdigit():
            return int(value)
    return None


def _project_ast_node(node: ClauseASTNode, result: list[dict]) -> None:
    result.append({
        "id": node.id,
        "standard_id": node.standard_id,
        "parent_id": node.parent_id,
        "clause_no": node.clause_no,
        "node_type": node.node_type,
        "node_key": node.node_key,
        "node_label": node.node_label,
        "clause_title": node.clause_title,
        "clause_text": node.clause_text,
        "summary": node.summary,
        "tags": node.tags,
        "page_start": _normalize_page_number(node.page_start),
        "page_end": _normalize_page_number(node.page_end),
        "clause_type": node.clause_type,
        "source_type": node.source_type or "text",
        "source_label": node.source_label,
        "source_ref": node.source_ref,
        "source_refs": node.source_refs,
    })
    for child in node.children:
        _project_ast_node(child, result)


def project_clause_ast(roots: list[ClauseASTNode]) -> list[dict]:
    """Project AST roots to persistence-facing clause dicts."""
    result: list[dict] = []
    for root in roots:
        _project_ast_node(root, result)
    return result


def build_tree(
    entries: list[dict],
    standard_id: UUID,
) -> list[dict]:
    """Build a hierarchical clause tree from extracted entries."""
    if not entries:
        return []

    roots = build_clause_ast(entries, standard_id)
    result = project_clause_ast(roots)

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
