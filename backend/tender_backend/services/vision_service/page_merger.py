"""Merge per-page vision extraction results, handling cross-page continuations."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def merge_page_results(
    pages: list[tuple[int, list[dict]]],
) -> list[dict]:
    """Merge per-page clause extractions into a unified entry list.

    Args:
        pages: Ordered list of ``(page_number, entries)`` tuples.  Each *entry*
            is a dict produced by the VL model with at least ``clause_no``,
            ``clause_text``, ``is_continuation``, and ``page_start``.

    Returns:
        Flat list of entry dicts ready for ``tree_builder.build_tree()``.
    """
    # Collect all entries; keyed by (clause_no, page_number) for look-back.
    merged: list[dict] = []
    # Map clause_no → last entry dict for that clause (used for continuation look-up).
    last_by_clause: dict[str, dict] = {}

    for page_number, entries in sorted(pages, key=lambda p: p[0]):
        for entry in entries:
            if entry.get("is_continuation") and entry.get("continuation_clause_no"):
                base = last_by_clause.get(entry["continuation_clause_no"])
                if base is not None:
                    _merge_continuation(base, entry)
                    logger.debug(
                        "merged continuation page=%d clause=%s",
                        page_number,
                        entry.get("continuation_clause_no"),
                    )
                    continue
                # No matching base found — keep as standalone and warn.
                logger.warning(
                    "orphan_continuation page=%d clause_no=%s — no base clause found, keeping as standalone",
                    page_number,
                    entry.get("continuation_clause_no"),
                )

            # Strip continuation-only fields before downstream processing.
            entry.pop("is_continuation", None)
            entry.pop("continuation_clause_no", None)
            merged.append(entry)

            # Track for future continuations (only clauses with a clause_no).
            clause_no = entry.get("clause_no")
            if clause_no:
                last_by_clause[clause_no] = entry

    return merged


def _merge_continuation(base: dict, continuation: dict) -> None:
    """Merge *continuation* into *base* in place.

    - Append ``clause_text``
    - Extend ``page_end``
    - Merge children if present
    """
    sep = "" if base.get("clause_text", "").endswith("\n") else "\n"
    base["clause_text"] = base.get("clause_text", "") + sep + continuation.get("clause_text", "")

    cont_page = continuation.get("page_end") or continuation.get("page_start")
    if cont_page:
        base["page_end"] = cont_page

    # Merge children lists.
    cont_children = continuation.get("children")
    if cont_children:
        base.setdefault("children", []).extend(cont_children)

    # Extend summary if the continuation adds meaningful info.
    cont_summary = continuation.get("summary", "")
    if cont_summary and cont_summary != base.get("summary", ""):
        base["summary"] = (base.get("summary") or "") + "；" + cont_summary
