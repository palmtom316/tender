"""Canonical normalizer for MinerU 2.7.x VLM/hybrid backend payloads.

Takes the `middle.json` (or equivalent dict) emitted by MinerU and produces
a stable, normalized structure keyed on `pages`, `tables`, `full_markdown`,
and `parser_version`. The rest of the ingestion pipeline consumes this
canonical shape so we never again have to probe half a dozen provider
variants inside block-extraction code.

Shape reference: `docs/superpowers/plans/2026-04-18-mineru-new-output-compatibility-plan-revision.md`
Real sample (2.7.6 / hybrid): `MinerU_GB50147_2010__20260418120949.json`
"""

from __future__ import annotations

from typing import Any


# LaTeX wrap strategy A — preserve equations, wrap inline in `$...$` and
# block-level equations with `$$...$$` so downstream LLMs and markdown
# renderers both read them correctly.
_INLINE_EQUATION_WRAP = "$"
_INTERLINE_EQUATION_WRAP_OPEN = "$$"
_INTERLINE_EQUATION_WRAP_CLOSE = "$$"

_SUPPORTED_BACKENDS = (None, "hybrid", "vlm")


def normalize_mineru_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical `{parser_version, pages, tables, full_markdown}` dict.

    Raises `ValueError` if the payload carries an unsupported `_backend`.
    Unknown/legacy shapes (e.g. pipeline backend) should be rejected rather
    than silently producing degraded output.
    """
    backend = payload.get("_backend")
    if backend not in _SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unsupported MinerU backend {backend!r}; "
            "normalizer handles hybrid/vlm only."
        )

    pdf_info = payload.get("pdf_info")
    pages = _extract_pages_from_pdf_info(pdf_info)
    tables = _extract_tables_from_pdf_info(pdf_info)

    raw_full_markdown = payload.get("full_markdown")
    if isinstance(raw_full_markdown, str) and raw_full_markdown.strip():
        full_markdown = raw_full_markdown
    else:
        full_markdown = "\n\n".join(page["markdown"] for page in pages if page.get("markdown"))

    return {
        "parser_version": payload.get("_version_name"),
        "pages": pages,
        "tables": tables,
        "full_markdown": full_markdown,
    }


# ── span/line text helpers ──

def _span_text(span: dict[str, Any]) -> str:
    span_type = span.get("type")
    if span_type == "table":
        # table HTML is routed through the tables channel, not inline text.
        return ""
    content = span.get("content")
    if not isinstance(content, str):
        return ""
    if span_type == "inline_equation":
        return f"{_INLINE_EQUATION_WRAP}{content}{_INLINE_EQUATION_WRAP}"
    if span_type == "interline_equation":
        return f"{_INTERLINE_EQUATION_WRAP_OPEN}{content}{_INTERLINE_EQUATION_WRAP_CLOSE}"
    return content


def _lines_text(lines: list[dict[str, Any]] | None) -> str:
    if not lines:
        return ""
    parts: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        spans = line.get("spans") or []
        joined = "".join(_span_text(s) for s in spans if isinstance(s, dict)).strip()
        if joined:
            parts.append(joined)
    return "\n".join(parts)


def _collect_block_text(block: dict[str, Any]) -> list[str]:
    """Return one text fragment per logical paragraph in reading order.

    Tables are skipped here so table HTML does not leak into markdown.
    `list` blocks (and any other container with `blocks[]`) are recursed into.
    """
    if not isinstance(block, dict):
        return []

    btype = block.get("type")
    if btype == "table":
        return []

    if btype == "list":
        nested: list[str] = []
        for child in block.get("blocks") or []:
            nested.extend(_collect_block_text(child))
        return nested

    lines = block.get("lines")
    if lines:
        text = _lines_text(lines)
        return [text] if text else []

    # Container block without inline lines (rare): recurse into children.
    children = block.get("blocks")
    if isinstance(children, list):
        nested = []
        for child in children:
            nested.extend(_collect_block_text(child))
        return nested

    return []


# ── page extraction ──

def _extract_pages_from_pdf_info(pdf_info: object) -> list[dict[str, Any]]:
    if not isinstance(pdf_info, list):
        return []
    pages: list[dict[str, Any]] = []
    for page in pdf_info:
        if not isinstance(page, dict):
            continue
        page_idx = page.get("page_idx")
        if not isinstance(page_idx, int):
            continue
        para_blocks = page.get("para_blocks")
        if not isinstance(para_blocks, list):
            continue
        fragments: list[str] = []
        for block in para_blocks:
            fragments.extend(_collect_block_text(block))
        markdown = "\n".join(fragment for fragment in fragments if fragment)
        if markdown:
            pages.append({"page_number": page_idx + 1, "markdown": markdown})
    return pages


# ── table extraction ──

def _extract_tables_from_pdf_info(pdf_info: object) -> list[dict[str, Any]]:
    if not isinstance(pdf_info, list):
        return []
    tables: list[dict[str, Any]] = []
    for page in pdf_info:
        if not isinstance(page, dict):
            continue
        page_idx = page.get("page_idx")
        if not isinstance(page_idx, int):
            continue
        for block in page.get("para_blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "table":
                continue
            caption = ""
            html = ""
            image_path = ""
            for child in block.get("blocks") or []:
                if not isinstance(child, dict):
                    continue
                child_type = child.get("type")
                if child_type == "table_caption":
                    caption_text = _lines_text(child.get("lines"))
                    if caption_text:
                        caption = caption_text
                elif child_type == "table_body":
                    for line in child.get("lines") or []:
                        for span in line.get("spans") or []:
                            if not isinstance(span, dict):
                                continue
                            if span.get("type") == "table":
                                html = span.get("html") or html
                                image_path = span.get("image_path") or image_path
            if not html:
                # Drop tables that have no HTML payload — they are unusable
                # downstream and would poison deterministic extraction.
                continue
            tables.append({
                "page_start": page_idx + 1,
                "page_end": page_idx + 1,
                "table_title": caption or None,
                "table_html": html,
                "table_image_path": image_path or None,
                "raw_json": block,
            })
    return tables
