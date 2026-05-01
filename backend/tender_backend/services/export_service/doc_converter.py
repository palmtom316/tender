"""Shared DOC conversion helper backed by LibreOffice headless."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import structlog

logger = structlog.stdlib.get_logger(__name__)


def convert_docx_to_doc(docx_path: Path) -> Path | None:
    """Convert a DOCX file to legacy DOC via LibreOffice/soffice.

    Returns the resulting .doc path on success, or None if the binary is
    unavailable or the conversion did not produce a file.
    """
    binary = shutil.which("libreoffice") or shutil.which("soffice")
    if binary is None:
        logger.warning("doc_conversion_unavailable", reason="libreoffice/soffice not found")
        return None
    result = subprocess.run(
        [
            binary,
            "--headless",
            "--convert-to",
            "doc",
            "--outdir",
            str(docx_path.parent),
            str(docx_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("doc_conversion_failed", stderr=result.stderr)
        return None
    doc_path = docx_path.with_suffix(".doc")
    return doc_path if doc_path.is_file() else None
