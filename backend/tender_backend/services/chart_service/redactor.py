from __future__ import annotations

from copy import deepcopy
from typing import Any


_SENSITIVE_KEYS = {
    "name",
    "person_name",
    "certificate_no",
    "cert_no",
    "id_no",
    "phone",
    "mobile",
    "email",
    "company_name",
    "project_location",
    "tender_no",
    "address",
    "contact",
    "client_name",
    "project_name",
}


def redact_context_for_chart(context: dict[str, Any], *, is_blind_bid: bool) -> dict[str, Any]:
    if not is_blind_bid:
        return deepcopy(context)
    return _redact_value(context)


def scan_blind_bid_keywords(spec_json: dict[str, Any], blacklist: list[str]) -> list[dict[str, str]]:
    text = _flatten_text(spec_json)
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for keyword in blacklist:
        cleaned = str(keyword or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        if cleaned in text:
            issues.append({"keyword": cleaned, "code": "blind_bid_sensitive_keyword"})
    return issues


def _redact_value(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for item_key, item_value in value.items():
            normalized_key = str(item_key)
            if normalized_key in _SENSITIVE_KEYS:
                result[normalized_key] = "[已脱敏]"
            else:
                result[normalized_key] = _redact_value(item_value, key=normalized_key)
        return result
    if isinstance(value, list):
        return [_redact_value(item, key=key) for item in value]
    return value


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_flatten_text(item) for item in value)
    if value is None:
        return ""
    return str(value)
