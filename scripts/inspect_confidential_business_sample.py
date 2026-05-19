#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from docx import Document


_CN_HEADING_RE = re.compile(r"^\s*(?P<code>[一二三四五六七八九十]+)、(?P<title>.+?)\s*$")
_NUMERIC_HEADING_RE = re.compile(r"^\s*(?P<code>\d+(?:\.\d+)*)(?:\.|．)(?P<title>[^\d.．].+?)\s*$")
_SENSITIVE_PATTERNS: dict[str, re.Pattern[str]] = {
    "mobile_phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_card": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "unified_social_credit_code": re.compile(r"\b[0-9A-Z]{18}\b"),
    "company_name": re.compile(r"[\u4e00-\u9fa5A-Za-z0-9（）()]{2,80}(?:公司|集团|分公司|有限责任公司)"),
    "project_name": re.compile(r"[\u4e00-\u9fa5A-Za-z0-9（）()]{2,80}(?:工程|项目|标段)"),
    "legal_representative": re.compile(r"(?:法定代表人|法人)\s*[:：]?\s*[\u4e00-\u9fa5]{2,4}"),
}


def _chinese_number_to_int(value: str) -> int | None:
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value == "十":
        return 10
    if value.startswith("十"):
        tail = value[1:]
        return 10 + (digits.get(tail, 0) if tail else 0)
    if "十" in value:
        head, tail = value.split("十", 1)
        if head not in digits:
            return None
        return digits[head] * 10 + (digits.get(tail, 0) if tail else 0)
    return digits.get(value)


def _normalize_heading_code(raw: str) -> str:
    if re.fullmatch(r"\d+(?:\.\d+)*", raw):
        return raw
    converted = _chinese_number_to_int(raw)
    return str(converted) if converted is not None else raw


def _heading_code(text: str) -> str | None:
    match = _CN_HEADING_RE.match(text)
    if match:
        return _normalize_heading_code(match.group("code"))
    match = _NUMERIC_HEADING_RE.match(text)
    if match:
        title = match.group("title").strip()
        if len(title) <= 60 and not title.endswith(("；", "。", "，", ";", ".")):
            return match.group("code")
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _paragraph_texts(path: Path) -> list[str]:
    document = Document(str(path))
    return [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]


def inspect_sample(path: str | Path) -> dict[str, Any]:
    docx_path = Path(path).expanduser().resolve()
    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX sample not found: {docx_path}")
    if docx_path.suffix.lower() != ".docx":
        raise ValueError(f"sample must be a DOCX file: {docx_path}")

    texts = _paragraph_texts(docx_path)
    heading_codes: list[str] = []
    seen_codes: set[str] = set()
    scan = {name: {"count": 0} for name in _SENSITIVE_PATTERNS}
    for text in texts:
        code = _heading_code(text)
        if code and code not in seen_codes:
            heading_codes.append(code)
            seen_codes.add(code)
        for name, pattern in _SENSITIVE_PATTERNS.items():
            scan[name]["count"] += len(pattern.findall(text))

    return {
        "docx_path": str(docx_path),
        "sha256": _sha256(docx_path),
        "size_bytes": docx_path.stat().st_size,
        "paragraph_count": len(texts),
        "heading_count": len(heading_codes),
        "heading_codes": heading_codes,
        "sensitive_scan": scan,
        "contains_sensitive_text": any(item["count"] > 0 for item in scan.values()),
        "text_redaction": "matched text is intentionally omitted",
    }


def to_json_text(evidence: dict[str, Any]) -> str:
    return json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a confidential business template DOCX without writing matched text.")
    parser.add_argument("--sample-docx", required=True, help="Local confidential DOCX path")
    parser.add_argument("--output", required=True, help="Sanitized evidence JSON output path")
    args = parser.parse_args()

    evidence = inspect_sample(args.sample_docx)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(to_json_text(evidence), encoding="utf-8")
    print(f"Wrote sanitized sample evidence to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
