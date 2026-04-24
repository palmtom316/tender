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
from tender_backend.services.norm_service.section_cleaning import (
    backfill_section_anchor,
    clean_sections,
    looks_like_backfilled_anchor,
    looks_like_front_matter_heading_noise,
    looks_like_suspicious_year_code,
    looks_like_toc_noise,
    looks_like_terminal_heading_noise,
    looks_like_unanchored_heading_noise,
)
from tender_backend.services.norm_service.norm_processor import _mineru_to_sections
from tender_backend.services.parse_service.mineru_normalizer import normalize_mineru_payload


_CLAUSE_LIKE_LINE_RE = re.compile(r"^\s*\d+(?:\.\d+){1,}\s+\S")


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
    toc_noise_count = sum(1 for section in sections if looks_like_toc_noise(section))
    front_matter_noise_count = sum(
        1 for section in sections if looks_like_front_matter_heading_noise(section)
    )
    suspicious_section_code_count = sum(
        1 for section in sections if looks_like_suspicious_year_code(section)
    )
    backfilled_anchor_count = sum(1 for section in sections if looks_like_backfilled_anchor(section))
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
    return clean_sections(sections, pages, drop_toc_noise=True)


def _clause_line_metrics(full_markdown: Any) -> tuple[int, int]:
    if not isinstance(full_markdown, str):
        return 0, 0
    clause_lines = [
        line.strip()
        for line in full_markdown.splitlines()
        if _CLAUSE_LIKE_LINE_RE.match(line.strip())
    ]
    return len(clause_lines), len(set(clause_lines))


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
