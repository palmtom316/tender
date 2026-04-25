"""Resolve standard parsing profiles from metadata and parse assets."""

from __future__ import annotations

import re
from typing import Any

from tender_backend.services.norm_service.document_assets import DocumentAsset
from tender_backend.services.norm_service.parse_profiles import (
    CN_GB_PROFILE,
    GENERIC_ENTERPRISE_PROFILE,
    ParseProfile,
    resolve_profile,
)


_CN_GB_CODE_RE = re.compile(r"\b(?:GB|GB/T|JGJ|DL/T|DL)\s*[- ]?\d+", re.I)
_GENERIC_ENTERPRISE_CODE_RE = re.compile(r"^(?:Q/|T/|REQ-|SEC-)", re.I)
_GENERIC_ENTERPRISE_TEXT_RE = re.compile(r"\b(?:REQ|SEC)-\d+\b")


def _standard_code(standard: dict | None) -> str:
    if not standard:
        return ""
    value = standard.get("standard_code") or standard.get("code") or ""
    return str(value).strip()


def _sample_text(document_asset: DocumentAsset | None) -> str:
    if document_asset is None:
        return ""
    if document_asset.full_markdown:
        return document_asset.full_markdown[:20000]
    parts = [
        str(page.normalized_text or "")
        for page in document_asset.pages[:20]
        if str(page.normalized_text or "").strip()
    ]
    return "\n".join(parts)[:20000]


def resolve_standard_profile(
    standard: dict | None,
    document_asset: DocumentAsset | None,
) -> ParseProfile:
    """Resolve the parse profile without relying on specific standard IDs."""
    code = _standard_code(standard)
    if _GENERIC_ENTERPRISE_CODE_RE.search(code):
        return GENERIC_ENTERPRISE_PROFILE
    if _CN_GB_CODE_RE.search(code):
        return CN_GB_PROFILE

    text = _sample_text(document_asset)
    if _GENERIC_ENTERPRISE_TEXT_RE.search(text):
        return GENERIC_ENTERPRISE_PROFILE
    if _CN_GB_CODE_RE.search(text) or "条文说明" in text:
        return CN_GB_PROFILE

    explicit_profile = None
    if standard:
        explicit_profile = standard.get("parse_profile") or standard.get("profile")
    return resolve_profile(str(explicit_profile).strip() if explicit_profile else None)


__all__ = ["resolve_standard_profile"]
