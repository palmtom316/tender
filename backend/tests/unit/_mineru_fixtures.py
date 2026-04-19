"""Shared MinerU test fixtures.

These builders mirror the real MinerU 2.7.x VLM/hybrid `pdf_info/para_blocks`
shape (see `MinerU_GB50147_2010_*.json`). Use them from
`test_mineru_normalizer.py`, `test_mineru_client.py`, and
`test_standard_mineru_batch_flow.py` so all three stay aligned with the
canonical structure.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from zipfile import ZipFile


def make_text_block(text: str, *, block_type: str = "text") -> dict[str, Any]:
    """A `{type, lines: [{spans: [{content, type}]}]}` block."""
    return {
        "type": block_type,
        "lines": [{"spans": [{"content": text, "type": "text"}]}],
    }


def make_table_block(
    *,
    caption: str = "",
    html: str = "",
    image_path: str = "",
    bbox: list[int] | None = None,
) -> dict[str, Any]:
    """A real-shape MinerU table block: caption + body sub-blocks, with the
    HTML living on a `type=table` span inside `table_body.lines[0].spans[0]`.
    """
    blocks: list[dict[str, Any]] = []
    if caption:
        blocks.append({
            "type": "table_caption",
            "lines": [{"spans": [{"content": caption, "type": "text"}]}],
        })
    span: dict[str, Any] = {"type": "table", "html": html}
    if image_path:
        span["image_path"] = image_path
    blocks.append({
        "type": "table_body",
        "lines": [{"spans": [span]}],
    })
    out: dict[str, Any] = {"type": "table", "blocks": blocks}
    if bbox is not None:
        out["bbox"] = bbox
    return out


def make_pdf_info_page(
    page_idx: int,
    para_blocks: list[dict[str, Any]],
    *,
    discarded_blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    page: dict[str, Any] = {"page_idx": page_idx, "para_blocks": para_blocks}
    if discarded_blocks is not None:
        page["discarded_blocks"] = discarded_blocks
    return page


def make_middle_json(
    pages: list[dict[str, Any]],
    *,
    backend: str = "hybrid",
    version: str = "2.7.6",
) -> dict[str, Any]:
    return {
        "_backend": backend,
        "_version_name": version,
        "pdf_info": pages,
    }


def make_simple_middle_json(
    page_idx: int = 0,
    *,
    title: str = "1 总则",
    body: str = "正文内容",
) -> dict[str, Any]:
    """Convenience: a one-page middle.json with a title block + body paragraph."""
    return make_middle_json([
        make_pdf_info_page(page_idx, [
            make_text_block(title, block_type="title"),
            make_text_block(body),
        ]),
    ])


def make_result_zip(
    middle_json: dict[str, Any],
    *,
    full_md: str = "",
    middle_filename: str = "spec_middle.json",
    extra_files: dict[str, str] | None = None,
) -> bytes:
    """Build a MinerU-style result zip with `full.md` + a `*_middle.json`."""
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("full.md", full_md)
        zf.writestr(middle_filename, json.dumps(middle_json))
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)
    return buf.getvalue()
