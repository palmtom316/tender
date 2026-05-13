from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_CHAPTER_HEADING_RE = re.compile(r"^(?P<index>[一二三四五六七八九十]+|\d+(?:\.\d+)*)(?:、|．|\.)(?P<title>.+)$")
_IGNORE_BLOCKS = {"（本页不编辑正文）"}


@dataclass(frozen=True)
class BusinessTemplatePreviewPage:
    page_number: int
    blocks: list[str]


@dataclass(frozen=True)
class BusinessTemplatePreviewChapter:
    chapter_code: str
    chapter_title: str
    page_start: int
    page_end: int
    pages: list[BusinessTemplatePreviewPage]


@dataclass(frozen=True)
class BusinessTemplatePreview:
    package_title: str
    chapters: list[BusinessTemplatePreviewChapter]


def _paragraph_text(paragraph: ET.Element) -> str:
    texts = [node.text or "" for node in paragraph.findall(".//w:t", _NS)]
    return "".join(texts).strip()


def _has_page_break(paragraph: ET.Element) -> bool:
    return paragraph.find(".//w:br[@w:type='page']", _NS) is not None


def _heading_match(text: str) -> tuple[str, str] | None:
    match = _CHAPTER_HEADING_RE.match(text.strip())
    if not match:
        return None
    return match.group("index"), match.group("title").strip()


def parse_business_template_preview(docx_path: Path) -> BusinessTemplatePreview:
    with ZipFile(docx_path) as archive:
        document_xml = archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    paragraphs = root.findall(".//w:body/w:p", _NS)

    chapters: list[BusinessTemplatePreviewChapter] = []
    current_code: str | None = None
    current_title: str | None = None
    current_page_number = 1
    current_page_blocks: list[str] = []
    current_pages: list[BusinessTemplatePreviewPage] = []
    current_page_start: int | None = None

    def flush_page() -> None:
        nonlocal current_page_blocks, current_pages, current_page_number
        if current_code is None:
            current_page_blocks = []
            return
        if current_page_blocks:
            current_pages.append(
                BusinessTemplatePreviewPage(
                    page_number=current_page_number,
                    blocks=current_page_blocks[:],
                )
            )
            current_page_blocks = []

    def flush_chapter() -> None:
        nonlocal current_pages, current_page_start, current_code, current_title
        flush_page()
        if current_code is None or current_title is None or not current_pages or current_page_start is None:
            return
        chapters.append(
            BusinessTemplatePreviewChapter(
                chapter_code=current_code,
                chapter_title=current_title,
                page_start=current_page_start,
                page_end=current_pages[-1].page_number,
                pages=current_pages[:],
            )
        )
        current_pages = []
        current_page_start = None

    for paragraph in paragraphs:
        text = _paragraph_text(paragraph)
        heading = _heading_match(text) if text else None

        if heading:
            flush_chapter()
            current_code, current_title = heading
            current_page_start = current_page_number
            current_page_blocks = []
        elif text and text not in _IGNORE_BLOCKS and current_code is not None:
            current_page_blocks.append(text)

        if _has_page_break(paragraph):
            flush_page()
            current_page_number += 1

    flush_chapter()

    return BusinessTemplatePreview(
        package_title=docx_path.stem,
        chapters=chapters,
    )
