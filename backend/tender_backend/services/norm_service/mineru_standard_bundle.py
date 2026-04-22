from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from tender_backend.services.norm_service.document_assets import (
    build_document_asset,
    serialize_document_asset,
)
from tender_backend.services.norm_service.norm_processor import _mineru_to_sections
from tender_backend.services.parse_service.mineru_normalizer import normalize_mineru_payload


_TOC_PAGE_MARKERS = ("目次", "contents")
_TOC_TITLE_RE = re.compile(r"\(\d+\)\s*$")
_YEAR_CODE_RE = re.compile(r"^(19|20)\d{2}$")
_CLAUSE_LIKE_LINE_RE = re.compile(r"^\s*\d+(?:\.\d+){1,}\s+\S")
_UNANCHORED_HEADING_RE = re.compile(r"^(?:附录[A-ZＡ-Ｚ]|[0-9]+(?:\.[0-9]+)*)(?:\s|$)")
_MULTISPACE_RE = re.compile(r"\s+")
_COMPACT_LEADING_CODE_RE = re.compile(r"^(\d+(?:\.\d+)*)(\S.*)$")
_FRONT_MATTER_MARKERS = (
    "中华人民共和国国家标准",
    "中国计划出版社",
    "目次",
    "contents",
    "发布",
    "实施",
    "isbn",
)
_FRONT_MATTER_TITLE_MARKERS = (
    "关于发布国家标准",
    "前言",
)
_TERMINAL_EXPLANATION_TITLES = (
    "本规范用词说明",
    "本标准用词说明",
)


@dataclass(frozen=True)
class StandardSampleInput:
    name: str
    pdf_path: Path
    md_path: Path
    json_path: Path


def build_standard_bundle(sample: StandardSampleInput) -> dict[str, Any]:
    payload = json.loads(sample.json_path.read_text(encoding="utf-8"))
    payload["full_markdown"] = sample.md_path.read_text(encoding="utf-8")
    normalized = normalize_mineru_payload(payload)

    document_id = uuid5(NAMESPACE_URL, f"file://{sample.pdf_path.resolve()}")
    sections = _mineru_to_sections(normalized["full_markdown"], normalized["pages"])
    section_rows = [
        {
            **section,
            "id": str(uuid5(NAMESPACE_URL, f"{document_id}:section:{index}")),
        }
        for index, section in enumerate(sections)
    ]
    table_rows = [
        {
            "id": str(uuid5(NAMESPACE_URL, f"{document_id}:table:{index}")),
            "section_id": None,
            "page": table.get("page_start"),
            "page_start": table.get("page_start"),
            "page_end": table.get("page_end"),
            "table_title": table.get("table_title"),
            "table_html": table.get("table_html"),
            "raw_json": table.get("raw_json"),
        }
        for index, table in enumerate(normalized["tables"])
    ]
    asset = build_document_asset(
        document_id=document_id,
        document={
            "id": document_id,
            "parser_name": "mineru",
            "parser_version": normalized.get("parser_version"),
            "raw_payload": normalized,
        },
        sections=section_rows,
        tables=table_rows,
    )
    serialized = serialize_document_asset(asset)

    return {
        "name": sample.name,
        "source_files": {
            "pdf": str(sample.pdf_path),
            "md": str(sample.md_path),
            "json": str(sample.json_path),
        },
        "document": _json_ready(serialized),
        "sections": _json_ready(section_rows),
        "tables": _json_ready(table_rows),
    }


def evaluate_standard_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    raw_payload = _bundle_raw_payload(bundle)
    sections = _bundle_sections(bundle)
    pages = raw_payload.get("pages") or []
    pdf_pages = _source_pdf_page_count(bundle)
    sections_with_page = sum(1 for section in sections if section.get("page_start") is not None)
    empty_text_sections = sum(1 for section in sections if not str(section.get("text") or "").strip())
    toc_noise_count = sum(1 for section in sections if _looks_like_toc_noise(section))
    front_matter_noise_count = sum(
        1 for section in sections if _looks_like_front_matter_heading_noise(section)
    )
    suspicious_section_code_count = sum(
        1 for section in sections if _looks_like_suspicious_year_code(section)
    )
    backfilled_anchor_count = sum(1 for section in sections if _looks_like_backfilled_anchor(section))
    clause_like_lines, clause_like_unique = _clause_line_metrics(raw_payload.get("full_markdown"))
    canonical_pages = len(pages)
    return {
        "name": str(bundle.get("name") or Path(bundle["source_files"]["pdf"]).stem),
        "pdf_pages": pdf_pages,
        "canonical_pages": canonical_pages,
        "page_coverage_ratio": canonical_pages / max(pdf_pages, 1),
        "tables": len(bundle.get("tables") or []),
        "sections": len(sections),
        "sections_with_page": sections_with_page,
        "section_page_coverage_ratio": sections_with_page / max(len(sections), 1),
        "empty_text_sections": empty_text_sections,
        "toc_noise_count": toc_noise_count,
        "front_matter_noise_count": front_matter_noise_count,
        "suspicious_section_code_count": suspicious_section_code_count,
        "backfilled_anchor_count": backfilled_anchor_count,
        "clause_like_lines": clause_like_lines,
        "clause_like_unique": clause_like_unique,
    }


def clean_standard_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(bundle)
    raw_payload = _bundle_raw_payload(cleaned)
    cleaned["sections"] = _clean_sections(cleaned.get("sections") or [], raw_payload.get("pages") or [])
    return cleaned


def compare_standard_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(summaries, key=lambda item: str(item.get("name") or ""))
    return {
        "sample_count": len(ordered),
        "samples": ordered,
    }


def write_bundle_outputs(
    output_dir: Path,
    *,
    bundle: dict[str, Any],
    summary: dict[str, Any],
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_payload_path = output_dir / "raw-payload.json"
    system_bundle_path = output_dir / "system-bundle.json"
    summary_path = output_dir / "summary.json"
    raw_payload_path.write_text(
        json.dumps(_bundle_raw_payload(bundle), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    system_bundle_path.write_text(
        json.dumps(_json_ready(bundle), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(_json_ready(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return [raw_payload_path, summary_path, system_bundle_path]


def write_compare_report(output_dir: Path, comparison: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "compare-report.md"
    lines = ["# MinerU Standard Bundle Comparison", ""]
    for sample in comparison.get("samples") or []:
        lines.append(
            f"- `{sample['name']}`: "
            f"toc_noise={sample.get('toc_noise_count', 0)}, "
            f"anchor_ratio={sample.get('section_page_coverage_ratio', 0)}"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _bundle_raw_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    document = bundle.get("document") or {}
    raw_payload = document.get("raw_payload")
    return raw_payload if isinstance(raw_payload, dict) else {}


def _bundle_sections(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    sections = bundle.get("sections")
    return sections if isinstance(sections, list) else []


def _source_pdf_page_count(bundle: dict[str, Any]) -> int:
    json_path = Path(bundle["source_files"]["json"])
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    pdf_info = payload.get("pdf_info")
    if not isinstance(pdf_info, list):
        return 0
    return sum(1 for item in pdf_info if isinstance(item, dict))


def _clean_sections(sections: list[dict[str, Any]], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for section in sections:
        if _looks_like_toc_noise(section):
            continue
        if _looks_like_suspicious_year_code(section):
            continue
        repaired = _backfill_section_anchor(section, pages)
        if _looks_like_front_matter_heading_noise(repaired):
            continue
        if _looks_like_unanchored_heading_noise(repaired):
            continue
        if _looks_like_terminal_heading_noise(repaired):
            continue
        cleaned.append(repaired)
    return cleaned


def _looks_like_toc_noise(section: dict[str, Any]) -> bool:
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    raw_json = section.get("raw_json") or {}
    markdown = str(raw_json.get("markdown") or "")
    lowered_markdown = markdown.lower()
    if not title or text:
        return False
    return (
        "目次" in markdown
        or "contents" in lowered_markdown
        or _TOC_TITLE_RE.search(title) is not None
    )


def _looks_like_front_matter_heading_noise(section: dict[str, Any]) -> bool:
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    raw_json = section.get("raw_json") or {}
    markdown = str(raw_json.get("markdown") or "").lower()
    if text:
        return False
    if title in {"目次", "Contents", "中华人民共和国国家标准"}:
        return True
    if any(marker in title for marker in _FRONT_MATTER_TITLE_MARKERS):
        return True
    if title.startswith("《"):
        return True
    return any(marker in markdown for marker in _FRONT_MATTER_MARKERS)


def _looks_like_suspicious_year_code(section: dict[str, Any]) -> bool:
    code = str(section.get("section_code") or "").strip()
    if not _YEAR_CODE_RE.match(code):
        return False
    raw_json = section.get("raw_json") or {}
    markdown = str(raw_json.get("markdown") or "")
    text = str(section.get("text") or "").strip()
    return (not text) or any(marker in markdown for marker in _FRONT_MATTER_MARKERS)


def _looks_like_backfilled_anchor(section: dict[str, Any]) -> bool:
    raw_json = section.get("raw_json")
    if not isinstance(raw_json, dict):
        return False
    page_number = raw_json.get("page_number")
    return (
        section.get("page_start") is not None
        and page_number == section.get("page_start")
        and "markdown" in raw_json
    )


def _looks_like_unanchored_heading_noise(section: dict[str, Any]) -> bool:
    if section.get("page_start") is not None:
        return False
    if str(section.get("text") or "").strip():
        return False
    if section.get("raw_json") is not None:
        return False
    title = str(section.get("title") or "").strip()
    return bool(title) and _UNANCHORED_HEADING_RE.match(title) is not None


def _looks_like_terminal_heading_noise(section: dict[str, Any]) -> bool:
    if section.get("page_start") is not None:
        return False
    if str(section.get("text") or "").strip():
        return False
    if section.get("raw_json") is not None:
        return False
    if str(section.get("section_code") or "").strip():
        return False
    title = str(section.get("title") or "").strip()
    if not title:
        return False
    if title in _TERMINAL_EXPLANATION_TITLES:
        return True
    if title == "电气装置安装工程":
        return True
    return (
        "电气装置安装工程" in title
        and any(marker in title for marker in ("施工及验收规范", "试验标准"))
    )


def _backfill_section_anchor(section: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    if section.get("page_start") is not None:
        return section
    title = str(section.get("title") or "").strip()
    code = str(section.get("section_code") or "").strip()
    heading = " ".join(part for part in (code, title) if part).strip()
    text = str(section.get("text") or "").strip()
    snippet = text.splitlines()[0].strip() if text else ""
    candidates = [
        candidate
        for candidate in (heading, title, snippet)
        if candidate and len(_normalize_for_match(candidate)) >= 4
    ]
    for candidate in list(candidates):
        for variant in _compact_heading_variants(candidate):
            if variant not in candidates:
                candidates.append(variant)
    matched = None
    for candidate in candidates:
        matches = _unique_page_matches(candidate, pages)
        if len(matches) == 1:
            matched = matches[0]
            break
    if matched is None:
        matched = _fallback_compact_heading_page(section, pages, candidates)
    if matched is None:
        matched = _fallback_appendix_heading_page(section, pages)
    if matched is None:
        return section
    return {
        **section,
        "page_start": matched.get("page_number"),
        "page_end": matched.get("page_number"),
        "raw_json": {
            "page_number": matched.get("page_number"),
            "markdown": matched.get("markdown"),
        },
    }


def _clause_line_metrics(full_markdown: Any) -> tuple[int, int]:
    if not isinstance(full_markdown, str):
        return 0, 0
    clause_lines = [
        line.strip()
        for line in full_markdown.splitlines()
        if _CLAUSE_LIKE_LINE_RE.match(line.strip())
    ]
    return len(clause_lines), len(set(clause_lines))


def _normalize_for_match(value: Any) -> str:
    text = str(value or "")
    text = _MULTISPACE_RE.sub("", text)
    return (
        text.replace("（", "(")
        .replace("）", ")")
        .replace("—", "-")
        .replace("–", "-")
        .replace("－", "-")
    )


def _unique_page_matches(candidate: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_candidate = _normalize_for_match(candidate)
    if not normalized_candidate:
        return []
    matches = []
    for page in pages:
        normalized_markdown = _normalize_for_match(page.get("markdown"))
        if normalized_markdown and normalized_candidate in normalized_markdown:
            matches.append(page)
    non_toc_matches = [page for page in matches if not _page_looks_like_toc(page)]
    if len({page.get("page_number") for page in non_toc_matches}) == 1:
        matches = non_toc_matches
    page_numbers = {page.get("page_number") for page in matches}
    if len(page_numbers) != 1:
        return []
    return matches[:1]


def _page_looks_like_toc(page: dict[str, Any]) -> bool:
    markdown = str(page.get("markdown") or "").lower()
    return any(marker in markdown for marker in _TOC_PAGE_MARKERS)


def _compact_heading_variants(candidate: str) -> list[str]:
    compact = str(candidate or "").strip()
    match = _COMPACT_LEADING_CODE_RE.match(compact)
    if not match:
        return []
    code, rest = match.groups()
    spaced = f"{code} {rest}".strip()
    variants = []
    if spaced != compact:
        variants.append(spaced)
    collapsed = f"{code}{rest}".strip()
    if collapsed != compact and collapsed not in variants:
        variants.append(collapsed)
    return variants


def _fallback_compact_heading_page(
    section: dict[str, Any],
    pages: list[dict[str, Any]],
    candidates: list[str],
) -> dict[str, Any] | None:
    if str(section.get("text") or "").strip():
        return None
    if section.get("raw_json") is not None:
        return None
    title = str(section.get("title") or "").strip()
    if not _COMPACT_LEADING_CODE_RE.match(title):
        return None
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized_candidate = _normalize_for_match(candidate)
        if not normalized_candidate:
            continue
        for page in pages:
            normalized_markdown = _normalize_for_match(page.get("markdown"))
            if normalized_markdown and normalized_candidate in normalized_markdown:
                matches.append(page)
    non_toc = [page for page in matches if not _page_looks_like_toc(page)]
    if not non_toc:
        return None
    return sorted(non_toc, key=lambda page: (page.get("page_number") or 0))[0]


def _fallback_appendix_heading_page(
    section: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if section.get("page_start") is not None:
        return None
    title = str(section.get("title") or "").strip()
    if not title.startswith("附录"):
        return None
    normalized_title = _normalize_for_match(title)
    if not normalized_title:
        return None
    matches = []
    for page in pages:
        normalized_markdown = _normalize_for_match(page.get("markdown"))
        if normalized_markdown and normalized_title in normalized_markdown:
            matches.append(page)
    non_toc = [page for page in matches if not _page_looks_like_toc(page)]
    if not non_toc:
        return None
    return sorted(non_toc, key=lambda page: (page.get("page_number") or 0))[0]


def _json_ready(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
