"""Merge local repair patches back into projected clause rows."""

from __future__ import annotations

from tender_backend.services.vision_service.repair_service import RepairPatch


def merge_repair_patches(clauses: list[dict], patches: list[RepairPatch]) -> list[dict]:
    """Apply local repair patches by source_ref.

    The first iteration keeps the merge conservative: only direct text replacement
    is applied for symbol/numeric repairs. Table patches are attached as metadata
    until the structured table AST merge lands.
    """
    if not patches:
        return clauses

    by_source_ref = {patch.source_ref: patch for patch in patches if patch.status == "patched"}
    if not by_source_ref:
        return clauses

    for clause in clauses:
        source_ref = clause.get("source_ref")
        if not isinstance(source_ref, str):
            continue
        patch = by_source_ref.get(source_ref)
        if patch is None:
            continue
        if patch.task_type == "symbol_numeric_repair" and patch.patched_text:
            clause["clause_text"] = patch.patched_text
            continue
        if patch.task_type == "table_repair" and patch.patched_table_html:
            clause.setdefault("repair_metadata", {})
            clause["repair_metadata"]["patched_table_html"] = patch.patched_table_html
            clause["repair_metadata"]["notes"] = patch.notes
    return clauses
