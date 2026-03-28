"""Deterministic semantic blocks for single-standard parsing experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re


_APPENDIX_CODE_RE = re.compile(r"^[A-Z](?:\.\d+)*$")
_LEADING_CLAUSE_NO_RE = re.compile(r"^\s*((?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)+))\b")
_LIST_ITEM_CODE_RE = re.compile(r"^\d+$")
_NON_CLAUSE_TITLE_RE = re.compile(r"^(本规范用词说明|引用标准名录|修订说明|目次|前言)$")
_NON_CLAUSE_TEXT_RE = re.compile(r"(为便于在执行本规范条文时区别对待|条文中指明应按其他有关标准执行)")
_TOC_PAGE_REF_RE = re.compile(r"(?:\(\d+\)|（\d+）)\s*$")
_TOC_DOT_LEADERS_RE = re.compile(r"[.…]{2,}")
_SECTION_TITLE_SENTENCE_SIGNAL_RE = re.compile(r"[，。；：]|应|不得|必须|严禁|禁止|宜|可")


@dataclass(slots=True)
class BlockSegment:
    segment_type: str
    chapter_label: str
    text: str
    page_start: int | None = None
    page_end: int | None = None
    clause_no: str | None = None
    table_title: str | None = None
    table_html: str | None = None
    section_ids: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    confidence: str = "high"


def _clause_depth(clause_no: str | None) -> int:
    if not clause_no:
        return 0
    return clause_no.count(".") + 1


def _section_label(section: dict) -> str:
    code = str(section.get("section_code") or "").strip()
    title = str(section.get("title") or "").strip()
    return f"{code} {title}".strip() or title or code or "未命名章节"


def _extract_clause_no(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _LEADING_CLAUSE_NO_RE.match(text)
    if not match:
        return None
    return match.group(1)


def _section_clause_no(section: dict) -> str | None:
    code = str(section.get("section_code") or "").strip()
    if code:
        return code
    return _extract_clause_no(section.get("title"))


def _section_effective_text(section: dict) -> str:
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    clause_no = _section_clause_no(section)
    if text:
        if title and clause_no and _LIST_ITEM_CODE_RE.match(clause_no):
            if title.endswith(("：", ":", "。", "；")):
                return f"{title}\n{text}".strip()
            return f"{title}{text}".strip()
        return text
    if not title or not clause_no or clause_no.count(".") < 2:
        return ""
    if _TOC_PAGE_REF_RE.search(title) or _TOC_DOT_LEADERS_RE.search(title):
        return ""
    if not _SECTION_TITLE_SENTENCE_SIGNAL_RE.search(title):
        return ""
    return title


def _is_numbered_list_item_section(section: dict) -> bool:
    code = str(section.get("section_code") or "").strip()
    if not code or not _LIST_ITEM_CODE_RE.match(code):
        return False
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    if not title and not text:
        return False
    if title and (_TOC_PAGE_REF_RE.search(title) or _TOC_DOT_LEADERS_RE.search(title)):
        return False
    return bool(text or _SECTION_TITLE_SENTENCE_SIGNAL_RE.search(title))


def _block_invites_numbered_list_items(block: BlockSegment) -> bool:
    if block.segment_type not in {"normative_clause_block", "commentary_block", "appendix_block"}:
        return False
    text = block.text.strip()
    if not text:
        return False
    return text.endswith(("：", ":")) or "下列" in text or "如下" in text


def _merge_numbered_list_item_into_block(block: BlockSegment, section: dict, *, text: str) -> None:
    code = str(section.get("section_code") or "").strip()
    item_text = f"{code} {text}".strip() if code else text
    block.text = f"{block.text.rstrip()}\n{item_text}".strip()
    block.page_end = section.get("page_end") or section.get("page_start") or block.page_end
    section_id = str(section.get("id") or "").strip()
    if section_id:
        block.section_ids.append(section_id)
        block.source_refs.append(f"document_section:{section_id}")
    block.confidence = "medium"


def _is_appendix(section: dict) -> bool:
    code = _section_clause_no(section)
    title = str(section.get("title") or "").strip()
    return bool((code and _APPENDIX_CODE_RE.match(code)) or title.startswith("附录"))


def _is_commentary(section: dict) -> bool:
    title = str(section.get("title") or "").strip()
    return "条文说明" in title


def _is_non_clause_section(section: dict) -> bool:
    title = str(section.get("title") or "").strip()
    if _NON_CLAUSE_TITLE_RE.match(title):
        return True
    text = str(section.get("text") or "").strip()
    combined = "\n".join(part for part in (title, text) if part)
    return bool(combined and _NON_CLAUSE_TEXT_RE.search(combined))


def _looks_like_commentary_clause(section: dict) -> bool:
    clause_no = _section_clause_no(section)
    if _clause_depth(clause_no) < 3:
        return False
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    return bool(text or title)


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


def _block_confidence(*, segment_type: str, clause_no: str | None, text: str, source_refs: list[str]) -> str:
    if segment_type == "heading_only_block":
        return "low"
    if segment_type == "table_requirement_block":
        return "medium"
    if segment_type == "commentary_block":
        return "high" if clause_no and text and source_refs else "medium"
    if segment_type == "appendix_block":
        return "medium" if text else "low"
    if clause_no and text and source_refs:
        return "high"
    return "medium"


def build_single_standard_blocks(sections: list[dict], tables: list[dict]) -> list[BlockSegment]:
    blocks: list[BlockSegment] = []
    in_commentary_tail = False
    list_host_block: BlockSegment | None = None

    for section in sections:
        section_id = str(section.get("id") or "").strip()
        text = _section_effective_text(section)
        title = str(section.get("title") or "").strip()
        label = _section_label(section)
        clause_no = _section_clause_no(section)
        if (
            list_host_block is not None
            and _is_numbered_list_item_section(section)
            and not _is_non_clause_section(section)
        ):
            _merge_numbered_list_item_into_block(list_host_block, section, text=text or title)
            continue
        if _is_commentary(section) and (clause_no or text):
            segment_type = "commentary_block"
        elif _is_non_clause_section(section):
            segment_type = "non_clause_block"
            if title in {"修订说明", "条文说明"}:
                in_commentary_tail = True
        elif in_commentary_tail and _looks_like_commentary_clause(section):
            segment_type = "commentary_block"
            if not text:
                text = title
        elif in_commentary_tail and _clause_depth(clause_no) < 3:
            segment_type = "non_clause_block"
        elif _is_appendix(section):
            segment_type = "appendix_block"
        elif _is_commentary(section):
            segment_type = "non_clause_block"
            in_commentary_tail = True
        elif not text:
            segment_type = "heading_only_block"
        else:
            segment_type = "normative_clause_block"

        source_refs = [f"document_section:{section_id}"] if section_id else []
        blocks.append(BlockSegment(
            segment_type=segment_type,
            chapter_label=label,
            text=text,
            page_start=section.get("page_start"),
            page_end=section.get("page_end"),
            clause_no=clause_no,
            section_ids=[section_id] if section_id else [],
            source_refs=source_refs,
            confidence=_block_confidence(
                segment_type=segment_type,
                clause_no=clause_no,
                text=text,
                source_refs=source_refs,
            ),
        ))
        list_host_block = blocks[-1] if _block_invites_numbered_list_items(blocks[-1]) else None

    for table in tables:
        table_id = str(table.get("id") or "").strip()
        title = str(table.get("table_title") or "").strip() or None
        source_refs = [f"table:{table_id}"] if table_id else []
        blocks.append(BlockSegment(
            segment_type="table_requirement_block",
            chapter_label=f"表格: {title or '未命名表格'}",
            text=_table_text(table),
            page_start=table.get("page_start") or table.get("page"),
            page_end=table.get("page_end") or table.get("page_start") or table.get("page"),
            table_title=title,
            table_html=str(table.get("table_html") or "").strip() or None,
            source_refs=source_refs,
            confidence=_block_confidence(
                segment_type="table_requirement_block",
                clause_no=None,
                text=_table_text(table),
                source_refs=source_refs,
            ),
        ))

    return blocks
