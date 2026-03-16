"""PDF exporter — converts DOCX to PDF.

Uses LibreOffice headless mode for conversion.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

logger = structlog.stdlib.get_logger(__name__)


def convert_docx_to_pdf(docx_path: Path, output_dir: Path | None = None) -> Path:
    """Convert a DOCX file to PDF using LibreOffice."""
    if output_dir is None:
        output_dir = docx_path.parent

    try:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", str(output_dir),
                str(docx_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("pdf_conversion_failed", stderr=result.stderr)
            raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")
    except FileNotFoundError:
        logger.warning("libreoffice_not_found", message="PDF conversion skipped — LibreOffice not installed")
        raise RuntimeError("LibreOffice not available for PDF conversion")

    pdf_path = output_dir / docx_path.with_suffix(".pdf").name
    logger.info("pdf_converted", output=str(pdf_path))
    return pdf_path
