"""Format validator — checks exported document against bid format requirements.

Validates font, size, spacing, margins extracted from bid document.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class FormatIssue:
    field: str
    expected: str
    actual: str
    severity: str = "P2"


@dataclass
class FormatRequirements:
    """Format requirements extracted from the bid document."""
    font_name: str | None = None          # e.g., "宋体"
    font_size: str | None = None           # e.g., "小四"
    line_spacing: str | None = None        # e.g., "1.5倍行距"
    margin_top: float | None = None        # mm
    margin_bottom: float | None = None
    margin_left: float | None = None
    margin_right: float | None = None
    page_size: str | None = None           # e.g., "A4"


def validate_format(
    template_path: str,
    requirements: FormatRequirements,
) -> list[FormatIssue]:
    """Validate that the DOCX template meets the format requirements.

    In production, reads the DOCX file and checks properties.
    Currently returns a stub validation.
    """
    issues: list[FormatIssue] = []

    # Placeholder: in production, would use python-docx to inspect the template
    # and compare against requirements.
    try:
        from docx import Document
        doc = Document(template_path)

        # Check page size (from section properties)
        for section in doc.sections:
            if requirements.page_size == "A4":
                # A4 = 210mm x 297mm ≈ 7560000 EMU x 10692000 EMU
                width_mm = section.page_width / 36000 if section.page_width else 0
                if abs(width_mm - 210) > 5:
                    issues.append(FormatIssue(
                        field="page_size",
                        expected="A4 (210mm)",
                        actual=f"{width_mm:.0f}mm",
                    ))

            if requirements.margin_left is not None:
                actual_mm = section.left_margin / 36000 if section.left_margin else 0
                if abs(actual_mm - requirements.margin_left) > 2:
                    issues.append(FormatIssue(
                        field="margin_left",
                        expected=f"{requirements.margin_left}mm",
                        actual=f"{actual_mm:.0f}mm",
                    ))
    except ImportError:
        logger.warning("python_docx_not_available", message="Detailed format validation skipped")
    except Exception as exc:
        logger.warning("format_validation_error", error=str(exc))

    logger.info("format_validated", issues=len(issues))
    return issues
