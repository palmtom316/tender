"""Build page-level text windows from document_section rows, filtering noise."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.stdlib.get_logger(__name__)

# Patterns treated as noise (headers, footers, page numbers, watermarks)
_NOISE_PATTERNS = [
    re.compile(r"^[\s]*-?\s*\d+\s*-?[\s]*$"),          # standalone page numbers
    re.compile(r"^[\s]*(第\s*\d+\s*页|Page\s*\d+)", re.I),  # "第X页" / "Page X"
    re.compile(r"^[\s]*[\d.]+[\s]*$"),                   # bare numbers / decimals
]

# Minimum meaningful text length per section
_MIN_TEXT_LENGTH = 8


@dataclass
class PageWindow:
    """A contiguous text block anchored to a page range."""

    page_start: int
    page_end: int
    text: str
    section_ids: list[str] = field(default_factory=list)


def _is_noise(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < _MIN_TEXT_LENGTH:
        return True
    return any(p.match(stripped) for p in _NOISE_PATTERNS)


def compress_sections(sections: list[dict]) -> list[PageWindow]:
    """Merge document_section rows into page-level windows.

    Each *section* dict is expected to have:
      id, text (or body), page_start, page_end, level, section_code, title
    """
    if not sections:
        return []

    # MinerU batch markdown currently persists legacy rows without page anchors.
    # In that case the fetch order is the best proxy for document order and must
    # be preserved; re-sorting by section code scrambles the standard.
    if all(s.get("page_start") is None for s in sections):
        sorted_secs = list(sections)
    else:
        sorted_secs = sorted(
            sections,
            key=lambda s: (
                s.get("page_start") or 0,
                s.get("level") or 0,
                s.get("section_code") or "",
            ),
        )

    windows: list[PageWindow] = []
    current: PageWindow | None = None

    for sec in sorted_secs:
        title = (sec.get("title") or "").strip()
        code = (sec.get("section_code") or "").strip()
        text = (sec.get("text") or sec.get("body") or "").strip()
        header = f"{code} {title}".strip()

        if text:
            if _is_noise(text):
                continue
            block = f"{header}\n{text}" if header else text
        else:
            level = sec.get("level") or 0
            if not header:
                continue
            if _is_noise(header) and level > 2:
                continue
            block = header

        page_s = sec.get("page_start") or 0
        page_e = sec.get("page_end") or page_s

        sid = str(sec.get("id", ""))

        if current is None or page_s > current.page_end + 1:
            # Start a new window
            current = PageWindow(
                page_start=page_s,
                page_end=page_e,
                text=block,
                section_ids=[sid],
            )
            windows.append(current)
        else:
            # Extend current window
            current.page_end = max(current.page_end, page_e)
            current.text += "\n\n" + block
            current.section_ids.append(sid)

    logger.info(
        "layout_compressed",
        input_sections=len(sections),
        output_windows=len(windows),
    )
    return windows
