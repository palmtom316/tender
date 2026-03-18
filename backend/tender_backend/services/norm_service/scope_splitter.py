"""Split compressed page windows into processing scopes.

Two scope types:
  - normative: main body clauses (hard constraints)
  - commentary: explanatory notes (条文说明)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from tender_backend.services.norm_service.layout_compressor import PageWindow

logger = structlog.stdlib.get_logger(__name__)

# Boundary patterns that signal the start of commentary sections
_COMMENTARY_BOUNDARIES = [
    re.compile(r"条文说明"),
    re.compile(r"附录\s*[A-Z]?\s*[（(]?资料性"),
    re.compile(r"本规范用词说明"),
    re.compile(r"引用标准名录"),
]

# Chapter heading patterns (e.g., "1 总则", "3.2 材料")
_CHAPTER_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)*)\s+\S",
    re.MULTILINE,
)


@dataclass
class ProcessingScope:
    """A slice of the standard document for one LLM call."""

    scope_type: str  # "normative" | "commentary"
    chapter_label: str  # e.g. "3 结构设计" or "条文说明"
    text: str
    page_start: int
    page_end: int
    section_ids: list[str] = field(default_factory=list)


def _detect_commentary_start(text: str) -> int | None:
    """Return char offset where commentary section begins, or None."""
    for pattern in _COMMENTARY_BOUNDARIES:
        m = pattern.search(text)
        if m:
            return m.start()
    return None


def _split_by_chapters(text: str, page_start: int, page_end: int,
                       section_ids: list[str], scope_type: str) -> list[ProcessingScope]:
    """Split a text block by top-level chapter headings."""
    matches = list(_CHAPTER_PATTERN.finditer(text))
    if not matches:
        return [ProcessingScope(
            scope_type=scope_type,
            chapter_label=scope_type,
            text=text,
            page_start=page_start,
            page_end=page_end,
            section_ids=section_ids,
        )]

    scopes: list[ProcessingScope] = []

    # Text before first chapter (preamble)
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            scopes.append(ProcessingScope(
                scope_type=scope_type,
                chapter_label="前言",
                text=preamble,
                page_start=page_start,
                page_end=page_start,
                section_ids=section_ids,
            ))

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if not chunk:
            continue

        # Extract chapter label from first line
        first_line = chunk.split("\n", 1)[0].strip()
        scopes.append(ProcessingScope(
            scope_type=scope_type,
            chapter_label=first_line[:60],
            text=chunk,
            page_start=page_start,
            page_end=page_end,
            section_ids=section_ids,
        ))

    return scopes


def split_into_scopes(windows: list[PageWindow]) -> list[ProcessingScope]:
    """Split page windows into normative and commentary scopes."""
    if not windows:
        return []

    # Concatenate all windows
    full_text = "\n\n".join(w.text for w in windows)
    all_ids = [sid for w in windows for sid in w.section_ids]
    first_page = windows[0].page_start
    last_page = windows[-1].page_end

    # Detect commentary boundary
    boundary = _detect_commentary_start(full_text)

    if boundary is not None:
        normative_text = full_text[:boundary].strip()
        commentary_text = full_text[boundary:].strip()
    else:
        normative_text = full_text
        commentary_text = ""

    scopes: list[ProcessingScope] = []

    # Split normative body by chapters
    if normative_text:
        scopes.extend(_split_by_chapters(
            normative_text, first_page, last_page, all_ids, "normative",
        ))

    # Split commentary by chapters
    if commentary_text:
        scopes.extend(_split_by_chapters(
            commentary_text, first_page, last_page, all_ids, "commentary",
        ))

    logger.info(
        "scopes_split",
        total_scopes=len(scopes),
        normative=[s.chapter_label for s in scopes if s.scope_type == "normative"],
        commentary=[s.chapter_label for s in scopes if s.scope_type == "commentary"],
    )
    return scopes
