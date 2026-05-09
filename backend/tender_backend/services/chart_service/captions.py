from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt


@dataclass
class FigureNumbering:
    _counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def next_number(self, *, chapter_code: str | None, explicit: str | None = None) -> str:
        if explicit:
            return explicit
        chapter = _chapter_segment(chapter_code)
        self._counts[chapter] += 1
        return f"图{chapter}-{self._counts[chapter]}"


def add_caption_after(paragraph, *, figure_no: str, title: str):
    caption = paragraph.insert_paragraph_before("")
    paragraph._element.addnext(caption._element)  # noqa: SLF001
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = caption.add_run(f"{figure_no} {title}".strip())
    run.font.size = Pt(9)
    run.font.name = "宋体"
    return caption


def _chapter_segment(chapter_code: str | None) -> str:
    if not chapter_code:
        return "1"
    match = re.search(r"\d+", chapter_code)
    return match.group(0) if match else "1"
