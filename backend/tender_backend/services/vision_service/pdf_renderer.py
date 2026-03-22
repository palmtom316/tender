"""Render PDF pages to PNG images using PyMuPDF."""

from __future__ import annotations

import base64
from dataclasses import dataclass

import fitz  # PyMuPDF


@dataclass
class PageImage:
    """A single rendered PDF page."""

    page_number: int  # 1-based
    png_bytes: bytes
    width: int
    height: int


def render_pdf_to_pages(pdf_path: str, *, dpi: int = 200) -> list[PageImage]:
    """Render every page of *pdf_path* to a PNG in memory.

    Args:
        pdf_path: Absolute path to a PDF file.
        dpi: Render resolution. 200 is a good balance for Chinese engineering
             standards (small table text stays legible, token cost stays sane).

    Returns:
        Ordered list of ``PageImage`` objects, one per page.
    """
    zoom = dpi / 72  # fitz default is 72 DPI
    mat = fitz.Matrix(zoom, zoom)

    pages: list[PageImage] = []
    with fitz.open(pdf_path) as doc:
        for idx in range(len(doc)):
            pix = doc.load_page(idx).get_pixmap(matrix=mat)
            pages.append(
                PageImage(
                    page_number=idx + 1,
                    png_bytes=pix.tobytes("png"),
                    width=pix.width,
                    height=pix.height,
                )
            )
    return pages


def encode_page_base64(page: PageImage) -> str:
    """Return a ``data:image/png;base64,...`` URI for OpenAI multimodal messages."""
    b64 = base64.b64encode(page.png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"
