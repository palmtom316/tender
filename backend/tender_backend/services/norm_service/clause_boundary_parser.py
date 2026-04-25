"""Deterministic clause-boundary parsing from normalized standard sections."""

from __future__ import annotations

import re
from typing import Any

from tender_backend.services.norm_service.parse_profiles import CN_GB_PROFILE, ParseProfile


_NUMERIC_CLAUSE_RE = re.compile(r"^\d+(?:\.\d+){2,}$")
_APPENDIX_CLAUSE_RE = re.compile(r"^[A-Z]\.\d+(?:\.\d+)*$")
_LIST_ITEM_RE = re.compile(r"^\d+$")
_COMMENTARY_TITLES = {"条文说明", "附：条文说明", "附:条文说明"}


def _section_id(section: dict) -> str:
    return str(section.get("id") or "").strip()


def _source_refs(section: dict) -> list[str]:
    section_id = _section_id(section)
    return [f"document_section:{section_id}"] if section_id else []


def _section_text(section: dict) -> str:
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    if title and text:
        return f"{title}\n{text}".strip()
    return text or title


def _is_list_host(text: str) -> bool:
    normalized = str(text or "").strip()
    return normalized.endswith(("：", ":")) or "下列" in normalized or "如下" in normalized


def _block_type(clause_no: str, *, in_commentary: bool) -> str:
    if in_commentary:
        return "commentary_clause"
    if _APPENDIX_CLAUSE_RE.match(clause_no):
        return "appendix_clause"
    return "clause"


def _new_clause_block(section: dict, *, clause_no: str, in_commentary: bool) -> dict[str, Any]:
    return {
        "block_id": _section_id(section) or clause_no,
        "block_type": _block_type(clause_no, in_commentary=in_commentary),
        "clause_no": clause_no,
        "clause_text": _section_text(section),
        "page_start": section.get("page_start"),
        "page_end": section.get("page_end") or section.get("page_start"),
        "source_refs": _source_refs(section),
        "confidence": "high",
        "items": [],
    }


def _new_item(section: dict) -> dict[str, Any]:
    return {
        "node_type": "item",
        "node_label": str(section.get("section_code") or "").strip(),
        "clause_text": _section_text(section),
        "source_refs": _source_refs(section),
    }


def _is_commentary_boundary(title: str, profile: ParseProfile) -> bool:
    normalized = str(title or "").strip().replace(" ", "")
    if normalized in _COMMENTARY_TITLES:
        return True
    return any(pattern.match(title.strip()) for pattern in profile.commentary_heading_patterns)


def parse_clause_blocks(
    sections: list[dict],
    tables: list[dict],
    *,
    profile: ParseProfile = CN_GB_PROFILE,
) -> list[dict]:
    """Parse clause-level blocks from normalized document sections.

    `tables` is accepted for the future table parser integration; this first
    boundary parser only emits text/commentary/appendix clause blocks.
    """
    blocks: list[dict] = []
    in_commentary = False
    active_list_host: dict | None = None

    for section in sections:
        title = str(section.get("title") or "").strip().replace(" ", "")
        if _is_commentary_boundary(title, profile):
            in_commentary = True
            active_list_host = None
            continue

        section_code = str(section.get("section_code") or "").strip()
        text = _section_text(section)
        if not text:
            continue

        if active_list_host is not None and _LIST_ITEM_RE.match(section_code):
            active_list_host["items"].append(_new_item(section))
            continue

        if _NUMERIC_CLAUSE_RE.match(section_code) or _APPENDIX_CLAUSE_RE.match(section_code):
            block = _new_clause_block(section, clause_no=section_code, in_commentary=in_commentary)
            blocks.append(block)
            active_list_host = block if not in_commentary and _is_list_host(block["clause_text"]) else None
            continue

        active_list_host = None

    return blocks
