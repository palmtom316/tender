"""Rebuild normative outline headings directly from page text."""

from __future__ import annotations

from dataclasses import dataclass
import re

from tender_backend.services.norm_service.document_assets import PageAsset

_COMMENTARY_BOUNDARY_PATTERNS = (
    re.compile(r"条文说明"),
    re.compile(r"本规范用词说明"),
    re.compile(r"引用标准名录"),
)
_TOC_HINT_PATTERNS = (
    re.compile(r"^\s*目次\s*$"),
    re.compile(r"^\s*contents\s*$", re.IGNORECASE),
)
_TOC_PAGE_REF = re.compile(r"(?:\(\d+\)|（\d+）)\s*$")
_TOC_DOT_LEADERS = re.compile(r"[.…]{2,}")
_FOOTER_PATTERNS = (
    re.compile(r"标准分享网"),
    re.compile(r"^·?\d+·?$"),
)
_IGNORE_LINES = {"text", "text_list", "title", "image", "table"}
_OUTLINE_HEADING_RE = re.compile(r"^(?P<code>\d+(?:\.\d+)?)\s*(?P<title>\S.*)$")
_APPENDIX_HEADING_RE = re.compile(r"^(?:附录)\s*(?P<code>[A-Z])\s*(?P<title>\S.*)$")
_TITLE_SENTENCE_PUNCT = ("。", "；", "：", "!", "?", "！", "？")
_MAX_TITLE_LENGTH = 30
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class OutlineMarker:
    section_code: str
    title: str
    level: int
    page_number: int | None
    page_index: int
    line_index: int
    line_text: str


def normalize_outline_page_lines(text: str | None) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() in _IGNORE_LINES:
            continue
        if any(pattern.search(line) for pattern in _FOOTER_PATTERNS):
            continue
        lines.append(line)
    return lines


def _is_toc_page(lines: list[str]) -> bool:
    if not lines:
        return False
    if any(pattern.search(lines[0]) for pattern in _TOC_HINT_PATTERNS):
        return True
    toc_like = sum(1 for line in lines if _TOC_PAGE_REF.search(line) or _TOC_DOT_LEADERS.search(line))
    return toc_like >= 2 and toc_like * 2 >= len(lines)


def _contains_commentary_boundary(lines: list[str]) -> bool:
    text = "\n".join(lines)
    return any(pattern.search(text) for pattern in _COMMENTARY_BOUNDARY_PATTERNS)


def _looks_like_outline_title(title: str) -> bool:
    stripped = title.strip()
    if not stripped:
        return False
    if stripped[0] in {".", "．", "。", ")", "）", "-", "\\", "/", "%"}:
        return False
    if len(stripped) > _MAX_TITLE_LENGTH:
        return False
    if any(mark in stripped for mark in _TITLE_SENTENCE_PUNCT):
        return False
    cjk_count = len(_CJK_RE.findall(stripped))
    if cjk_count < 2:
        return False
    if cjk_count * 2 < len(stripped):
        return False
    return True


def rebuild_outline_sections_from_pages(pages: list[PageAsset]) -> list[dict]:
    """Extract chapter/section headings from raw normative page text."""
    return [
        {
            "id": f"rebuilt-outline:{marker.section_code}",
            "section_code": marker.section_code,
            "title": marker.title,
            "level": marker.level,
            "page_start": marker.page_number,
            "page_end": marker.page_number,
            "text": "",
            "sort_order": index,
            "text_source": "rebuilt_page_outline",
        }
        for index, marker in enumerate(collect_outline_markers_from_pages(pages))
    ]


def collect_outline_markers_from_pages(pages: list[PageAsset]) -> list[OutlineMarker]:
    """Extract ordered chapter/section markers from raw normative page text."""
    sections: list[dict] = []
    seen_codes: set[str] = set()

    ordered_pages = sorted(
        pages,
        key=lambda page: (
            page.page_number if isinstance(page.page_number, int) else 10**9,
            page.source_ref,
        ),
    )

    markers: list[OutlineMarker] = []
    for page_index, page in enumerate(ordered_pages):
        lines = normalize_outline_page_lines(page.normalized_text)
        if not lines or _is_toc_page(lines):
            continue
        if _contains_commentary_boundary(lines):
            break

        for line_index, line in enumerate(lines):
            code: str | None = None
            title: str | None = None
            level: int | None = None

            match = _OUTLINE_HEADING_RE.match(line)
            if match:
                code = match.group("code")
                title = match.group("title").strip()
                level = code.count(".") + 1
                if code.count(".") > 1:
                    continue
                parts = code.split(".")
                if any(not part or len(part) > 2 or part.startswith("0") for part in parts):
                    continue
            else:
                appendix_match = _APPENDIX_HEADING_RE.match(line)
                if appendix_match:
                    code = appendix_match.group("code").strip()
                    title = appendix_match.group("title").strip()
                    level = 1

            if not code or not title or level is None:
                continue
            if code in seen_codes:
                continue
            if not _looks_like_outline_title(title):
                continue

            seen_codes.add(code)
            markers.append(
                OutlineMarker(
                    section_code=code,
                    title=title,
                    level=level,
                    page_number=page.page_number,
                    page_index=page_index,
                    line_index=line_index,
                    line_text=line,
                )
            )

    return markers


def collect_outline_clause_nos_from_pages(pages: list[PageAsset]) -> set[str]:
    return {
        marker.section_code.strip()
        for marker in collect_outline_markers_from_pages(pages)
        if marker.section_code
    }
