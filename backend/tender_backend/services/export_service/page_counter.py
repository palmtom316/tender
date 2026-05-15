"""DOCX page counting with explicit fallback states."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import shutil
import subprocess
import tempfile

import fitz


def count_docx_pages(docx_path: Path) -> dict[str, Any]:
    """Count DOCX pages via LibreOffice-rendered PDF, or return explicit unchecked evidence."""

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return {
            "status": "unchecked",
            "actual_pages": None,
            "method": "libreoffice_pdf_unavailable",
            "message": "LibreOffice 不可用，无法自动统计真实页数。",
        }

    with tempfile.TemporaryDirectory(prefix="tender-page-count-") as tmp:
        tmpdir = Path(tmp)
        completed = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(tmpdir), str(docx_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
        pdf_path = tmpdir / f"{docx_path.stem}.pdf"
        if not pdf_path.exists() and docx_path.with_suffix(".pdf").exists():
            # Supports tests and callers that pre-create the converted PDF beside the DOCX.
            pdf_path = docx_path.with_suffix(".pdf")
        if completed.returncode != 0 or not pdf_path.exists():
            return {
                "status": "unchecked",
                "actual_pages": None,
                "method": "libreoffice_pdf_failed",
                "message": getattr(completed, "stderr", "") or getattr(completed, "stdout", "") or "LibreOffice 转 PDF 失败。",
            }

        document = fitz.open(str(pdf_path))
        try:
            pages = len(document)
        finally:
            document.close()

    return {
        "status": "counted",
        "actual_pages": pages,
        "method": "libreoffice_pdf_pymupdf",
        "message": f"DOCX 转 PDF 后统计为 {pages} 页。",
    }
