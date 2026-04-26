from __future__ import annotations

import re
from typing import Any


_TOC_PAGE_MARKERS = ("目次", "contents")
_TOC_TITLE_RE = re.compile(r"\(\d+\)\s*$")
_YEAR_CODE_RE = re.compile(r"^(19|20)\d{2}$")
_UNANCHORED_HEADING_RE = re.compile(r"^(?:附录[A-ZＡ-Ｚ]|[0-9]+(?:\.[0-9]+)*)(?:\s|$)")
_MULTISPACE_RE = re.compile(r"\s+")
_COMPACT_LEADING_CODE_RE = re.compile(r"^(\d+(?:\.\d+)*)(\S.*)$")
_FRONT_MATTER_MARKERS = (
    "中华人民共和国国家标准",
    "中国计划出版社",
    "目次",
    "contents",
    "发布",
    "实施",
    "isbn",
)
_FRONT_MATTER_TITLE_MARKERS = (
    "关于发布国家标准",
    "前言",
)
_TERMINAL_EXPLANATION_TITLES = (
    "本规范用词说明",
    "本标准用词说明",
)


def clean_sections(
    sections: list[dict[str, Any]],
    pages: list[dict[str, Any]] | None = None,
    *,
    drop_toc_noise: bool = True,
) -> list[dict[str, Any]]:
    """Drop high-confidence OCR heading noise and backfill missing section anchors."""
    anchor_pages = pages if pages is not None else derive_anchor_pages(sections)
    cleaned: list[dict[str, Any]] = []
    for section in sections:
        if drop_toc_noise and looks_like_toc_noise(section):
            continue
        if looks_like_suspicious_year_code(section):
            continue
        repaired = repair_toc_anchored_section(section, anchor_pages)
        repaired = backfill_section_anchor(repaired, anchor_pages)
        if looks_like_front_matter_heading_noise(repaired):
            continue
        if looks_like_unanchored_heading_noise(repaired):
            continue
        if looks_like_terminal_heading_noise(repaired):
            continue
        cleaned.append(repaired)
    return cleaned


def derive_anchor_pages(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pages: dict[int, dict[str, Any]] = {}
    synthetic_pages: list[dict[str, Any]] = []
    for section in sections:
        raw_json = section.get("raw_json")
        raw_page = raw_json if isinstance(raw_json, dict) else None
        page_number = (raw_page or {}).get("page_number") or section.get("page_start")
        markdown = (raw_page or {}).get("markdown")
        if isinstance(page_number, int) and page_number > 0 and isinstance(markdown, str) and markdown.strip():
            pages.setdefault(page_number, {"page_number": page_number, "markdown": markdown})
            continue

        built_markdown = _build_section_markdown(section)
        if not built_markdown:
            continue
        if not isinstance(page_number, int) or page_number <= 0:
            continue
        synthetic_pages.append(
            {
                "page_number": page_number,
                "markdown": built_markdown,
            }
        )

    ordered_pages = [pages[page_number] for page_number in sorted(pages)]
    return ordered_pages + synthetic_pages


def looks_like_toc_noise(section: dict[str, Any]) -> bool:
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    raw_json = section.get("raw_json") or {}
    markdown = str(raw_json.get("markdown") or "")
    lowered_markdown = markdown.lower()
    if not title or text:
        return False
    return (
        "目次" in markdown
        or "contents" in lowered_markdown
        or _TOC_TITLE_RE.search(title) is not None
    )


def looks_like_front_matter_heading_noise(section: dict[str, Any]) -> bool:
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    raw_json = section.get("raw_json") or {}
    markdown = str(raw_json.get("markdown") or "").lower()
    if text:
        return False
    if title in {"目次", "Contents", "中华人民共和国国家标准"}:
        return True
    if any(marker in title for marker in _FRONT_MATTER_TITLE_MARKERS):
        return True
    if title.startswith("《"):
        return True
    return any(marker in markdown for marker in _FRONT_MATTER_MARKERS)


def looks_like_suspicious_year_code(section: dict[str, Any]) -> bool:
    code = str(section.get("section_code") or "").strip()
    if not _YEAR_CODE_RE.match(code):
        return False
    raw_json = section.get("raw_json") or {}
    markdown = str(raw_json.get("markdown") or "")
    text = str(section.get("text") or "").strip()
    return (not text) or any(marker in markdown for marker in _FRONT_MATTER_MARKERS)


def looks_like_backfilled_anchor(section: dict[str, Any]) -> bool:
    raw_json = section.get("raw_json")
    if not isinstance(raw_json, dict):
        return False
    page_number = raw_json.get("page_number")
    return (
        section.get("page_start") is not None
        and page_number == section.get("page_start")
        and "markdown" in raw_json
    )


def looks_like_unanchored_heading_noise(section: dict[str, Any]) -> bool:
    if section.get("page_start") is not None:
        return False
    if str(section.get("text") or "").strip():
        return False
    if section.get("raw_json") is not None:
        return False
    title = str(section.get("title") or "").strip()
    if not title or _UNANCHORED_HEADING_RE.match(title) is None:
        return False
    if title.startswith("附录"):
        return True
    match = re.match(r"^([0-9]+(?:\.[0-9]+)*)", title)
    if not match:
        return False
    return "." in match.group(1)


def looks_like_terminal_heading_noise(section: dict[str, Any]) -> bool:
    if section.get("page_start") is not None:
        return False
    if str(section.get("text") or "").strip():
        return False
    if section.get("raw_json") is not None:
        return False
    if str(section.get("section_code") or "").strip():
        return False
    title = str(section.get("title") or "").strip()
    if not title:
        return False
    if title in _TERMINAL_EXPLANATION_TITLES:
        return True
    if title == "电气装置安装工程":
        return True
    return (
        "电气装置安装工程" in title
        and any(marker in title for marker in ("施工及验收规范", "试验标准"))
    )


def backfill_section_anchor(section: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    if section.get("page_start") is not None:
        return section
    title = str(section.get("title") or "").strip()
    code = str(section.get("section_code") or "").strip()
    heading = " ".join(part for part in (code, title) if part).strip()
    text = str(section.get("text") or "").strip()
    snippet = text.splitlines()[0].strip() if text else ""
    candidates = [
        candidate
        for candidate in (heading, title, snippet)
        if candidate and len(_normalize_for_match(candidate)) >= 3
    ]
    for candidate in list(candidates):
        for variant in _compact_heading_variants(candidate):
            if variant not in candidates:
                candidates.append(variant)
    matched = None
    for candidate in candidates:
        matches = _unique_page_matches(candidate, pages)
        if len(matches) == 1:
            matched = matches[0]
            break
    if matched is None:
        matched = _fallback_compact_heading_page(section, pages, candidates)
    if matched is None:
        matched = _fallback_appendix_heading_page(section, pages)
    if matched is None:
        return section
    return {
        **section,
        "page_start": matched.get("page_number"),
        "page_end": matched.get("page_number"),
        "raw_json": {
            "page_number": matched.get("page_number"),
            "markdown": matched.get("markdown"),
        },
    }


def repair_toc_anchored_section(section: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    raw_json = section.get("raw_json")
    if not isinstance(raw_json, dict):
        return section
    markdown = str(raw_json.get("markdown") or "")
    if not markdown or not _page_looks_like_toc({"markdown": markdown}):
        return section
    stripped_section = {
        **section,
        "page_start": None,
        "page_end": None,
        "raw_json": None,
    }
    repaired = backfill_section_anchor(stripped_section, pages)
    if repaired.get("page_start") is None:
        return section
    if repaired.get("page_start") == section.get("page_start"):
        return section
    return repaired


def _build_section_markdown(section: dict[str, Any]) -> str | None:
    code = str(section.get("section_code") or "").strip()
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or section.get("body") or "").strip()
    heading = f"{code} {title}".strip()
    if heading and text:
        return f"{heading}\n{text}"
    if heading:
        return heading
    if text:
        return text
    return None


def _normalize_for_match(value: Any) -> str:
    text = str(value or "")
    text = _MULTISPACE_RE.sub("", text)
    return (
        text.replace("（", "(")
        .replace("）", ")")
        .replace("—", "-")
        .replace("–", "-")
        .replace("－", "-")
    )


def _unique_page_matches(candidate: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_candidate = _normalize_for_match(candidate)
    if not normalized_candidate:
        return []
    matches = []
    for page in pages:
        normalized_markdown = _normalize_for_match(page.get("markdown"))
        if normalized_markdown and normalized_candidate in normalized_markdown:
            matches.append(page)
    non_toc_matches = [page for page in matches if not _page_looks_like_toc(page)]
    if len({page.get("page_number") for page in non_toc_matches}) == 1:
        matches = non_toc_matches
    page_numbers = {page.get("page_number") for page in matches}
    if len(page_numbers) != 1:
        return []
    return matches[:1]


def _page_looks_like_toc(page: dict[str, Any]) -> bool:
    markdown = str(page.get("markdown") or "").lower()
    return any(marker in markdown for marker in _TOC_PAGE_MARKERS)


def _compact_heading_variants(candidate: str) -> list[str]:
    compact = str(candidate or "").strip()
    match = _COMPACT_LEADING_CODE_RE.match(compact)
    if not match:
        return []
    code, rest = match.groups()
    spaced = f"{code} {rest}".strip()
    variants = []
    if spaced != compact:
        variants.append(spaced)
    collapsed = f"{code}{rest}".strip()
    if collapsed != compact and collapsed not in variants:
        variants.append(collapsed)
    return variants


def _fallback_compact_heading_page(
    section: dict[str, Any],
    pages: list[dict[str, Any]],
    candidates: list[str],
) -> dict[str, Any] | None:
    if str(section.get("text") or "").strip():
        return None
    if section.get("raw_json") is not None:
        return None
    title = str(section.get("title") or "").strip()
    if not _COMPACT_LEADING_CODE_RE.match(title):
        return None
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized_candidate = _normalize_for_match(candidate)
        if not normalized_candidate:
            continue
        for page in pages:
            normalized_markdown = _normalize_for_match(page.get("markdown"))
            if normalized_markdown and normalized_candidate in normalized_markdown:
                matches.append(page)
    non_toc = [page for page in matches if not _page_looks_like_toc(page)]
    if not non_toc:
        return None
    return sorted(non_toc, key=lambda page: (page.get("page_number") or 0))[0]


def _fallback_appendix_heading_page(
    section: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if section.get("page_start") is not None:
        return None
    title = str(section.get("title") or "").strip()
    if not title.startswith("附录"):
        return None
    normalized_title = _normalize_for_match(title)
    if not normalized_title:
        return None
    matches = []
    for page in pages:
        normalized_markdown = _normalize_for_match(page.get("markdown"))
        if normalized_markdown and normalized_title in normalized_markdown:
            matches.append(page)
    non_toc = [page for page in matches if not _page_looks_like_toc(page)]
    if not non_toc:
        return None
    return sorted(non_toc, key=lambda page: (page.get("page_number") or 0))[0]
