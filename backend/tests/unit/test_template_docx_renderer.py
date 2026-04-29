from __future__ import annotations

from pathlib import Path

from tender_backend.services.template_service.docx_renderer import _sanitize_filename


def test_sanitize_filename_removes_unsafe_characters() -> None:
    assert _sanitize_filename("5.1_基本情况表.docx") == "5.1__.docx"
    assert _sanitize_filename("  ") == "rendered"


def test_sanitize_filename_keeps_ascii_safe_parts() -> None:
    assert _sanitize_filename("6.1_people-summary.docx") == "6.1_people-summary.docx"
