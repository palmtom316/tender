"""AI-free entry point for deterministic standard parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from tender_backend.services.norm_service.clause_boundary_parser import parse_clause_blocks
from tender_backend.services.norm_service.document_assets import (
    DocumentAsset,
    build_document_asset,
)
from tender_backend.services.norm_service.parse_profiles import ParseProfile
from tender_backend.services.norm_service.profile_resolver import resolve_standard_profile


@dataclass(frozen=True)
class GeneralStandardParseResult:
    profile: ParseProfile
    blocks: list[dict[str, Any]]
    metrics: dict[str, Any]
    ai_required: bool = False


def _document_id(document: dict | None) -> UUID:
    raw_id = (document or {}).get("id")
    if raw_id:
        try:
            return UUID(str(raw_id))
        except ValueError:
            pass
    return uuid4()


def _with_backfilled_page_anchors(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchored: list[dict[str, Any]] = []
    previous_page: int | None = None
    for block in blocks:
        current = dict(block)
        page_start = current.get("page_start")
        page_end = current.get("page_end")
        if isinstance(page_start, int):
            previous_page = page_start
        elif previous_page is not None:
            current["page_start"] = previous_page
        if not isinstance(page_end, int):
            current["page_end"] = current.get("page_start")
        anchored.append(current)
    return anchored


def _anchor_coverage(blocks: list[dict[str, Any]]) -> float:
    if not blocks:
        return 0.0
    anchored = sum(
        1
        for block in blocks
        if isinstance(block.get("page_start"), int) and isinstance(block.get("page_end"), int)
    )
    return anchored / len(blocks)


def _metrics(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    clause_blocks = [
        block
        for block in blocks
        if block.get("block_type") in {"clause", "appendix_clause", "commentary_clause"}
    ]
    clause_keys = [
        f"{block.get('block_type')}:{block.get('clause_no')}"
        for block in clause_blocks
        if str(block.get("clause_no") or "").strip()
    ]
    duplicate_clause_nos = sorted(
        key
        for key in set(clause_keys)
        if key and clause_keys.count(key) > 1
    )
    return {
        "block_count": len(blocks),
        "clause_count": len(clause_blocks),
        "anchor_coverage": _anchor_coverage(clause_blocks),
        "duplicate_clause_nos": duplicate_clause_nos,
        "validation_issue_count": len(duplicate_clause_nos),
        "ai_fallback_ratio": 0.0,
    }


def _build_asset(
    *,
    document: dict | None,
    sections: list[dict],
    tables: list[dict],
) -> DocumentAsset | None:
    return build_document_asset(
        document_id=_document_id(document),
        document=document or {},
        sections=sections,
        tables=tables,
    )


def parse_general_standard_document(
    *,
    standard: dict | None,
    document: dict | None,
    sections: list[dict],
    tables: list[dict],
) -> GeneralStandardParseResult:
    """Parse normalized standard assets into deterministic clause blocks."""
    document_asset = _build_asset(document=document, sections=sections, tables=tables)
    profile = resolve_standard_profile(standard, document_asset)
    blocks = parse_clause_blocks(sections, tables, profile=profile)
    blocks = _with_backfilled_page_anchors(blocks)
    return GeneralStandardParseResult(
        profile=profile,
        blocks=blocks,
        metrics=_metrics(blocks),
        ai_required=False,
    )


__all__ = ["GeneralStandardParseResult", "parse_general_standard_document"]
