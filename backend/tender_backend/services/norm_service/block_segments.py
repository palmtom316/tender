"""Deterministic semantic blocks for single-standard parsing experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re


_APPENDIX_CODE_RE = re.compile(r"^[A-Z](?:\.\d+)*$")
_COMMENTARY_TITLE_RE = re.compile(r"条文说明|说明$")


@dataclass(slots=True)
class BlockSegment:
    segment_type: str
    chapter_label: str
    text: str
    page_start: int | None = None
    page_end: int | None = None
    clause_no: str | None = None
    table_title: str | None = None
    section_ids: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    confidence: str = "high"


def _section_label(section: dict) -> str:
    code = str(section.get("section_code") or "").strip()
    title = str(section.get("title") or "").strip()
    return f"{code} {title}".strip() or title or code or "未命名章节"


def _section_clause_no(section: dict) -> str | None:
    code = str(section.get("section_code") or "").strip()
    return code or None


def _is_appendix(section: dict) -> bool:
    code = _section_clause_no(section)
    title = str(section.get("title") or "").strip()
    return bool((code and _APPENDIX_CODE_RE.match(code)) or ("附录" in title))


def _is_commentary(section: dict) -> bool:
    title = str(section.get("title") or "").strip()
    return bool(_COMMENTARY_TITLE_RE.search(title))


def _table_text(table: dict) -> str:
    parts: list[str] = []
    title = str(table.get("table_title") or "").strip()
    if title:
        parts.append(title)
    html = str(table.get("table_html") or "").strip()
    if html:
        parts.append(html)
    raw_json = table.get("raw_json")
    if raw_json:
        parts.append(json.dumps(raw_json, ensure_ascii=False))
    return "\n".join(parts).strip()


def build_single_standard_blocks(sections: list[dict], tables: list[dict]) -> list[BlockSegment]:
    blocks: list[BlockSegment] = []

    for section in sections:
        section_id = str(section.get("id") or "").strip()
        text = str(section.get("text") or "").strip()
        label = _section_label(section)
        clause_no = _section_clause_no(section)
        if _is_appendix(section):
            segment_type = "appendix_block"
        elif _is_commentary(section):
            segment_type = "commentary_block"
        elif not text:
            segment_type = "heading_only_block"
        else:
            segment_type = "normative_clause_block"

        blocks.append(BlockSegment(
            segment_type=segment_type,
            chapter_label=label,
            text=text,
            page_start=section.get("page_start"),
            page_end=section.get("page_end"),
            clause_no=clause_no,
            section_ids=[section_id] if section_id else [],
            source_refs=[f"document_section:{section_id}"] if section_id else [],
        ))

    for table in tables:
        table_id = str(table.get("id") or "").strip()
        title = str(table.get("table_title") or "").strip() or None
        blocks.append(BlockSegment(
            segment_type="table_requirement_block",
            chapter_label=f"表格: {title or '未命名表格'}",
            text=_table_text(table),
            page_start=table.get("page_start") or table.get("page"),
            page_end=table.get("page_end") or table.get("page_start") or table.get("page"),
            table_title=title,
            source_refs=[f"table:{table_id}"] if table_id else [],
        ))

    return blocks
