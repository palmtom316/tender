# MinerU Standard Bundle Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repo-local draft skill plus a deterministic CLI that converts MinerU `2.7.x` `hybrid/vlm` standard assets into parse-asset-like bundles, evaluates quality, cleans deterministic noise, and compares multiple standards.

**Architecture:** Keep the core logic in a small backend helper module so it can reuse existing repo functions (`normalize_mineru_payload`, `_mineru_to_sections`, `build_document_asset`, `serialize_document_asset`) and stay easy to unit-test. Put a thin CLI wrapper under `docs/skills/mineru-standard-bundle/scripts/`, then add a draft `SKILL.md` that teaches future sessions when to trigger the workflow and which commands to run.

**Tech Stack:** Python 3.14 virtualenv in `.venv`, pytest, repo-local backend helpers, JSON/Markdown file output, deterministic regex and page-matching cleanup only.

---

## File Map

**Create:**

- `backend/tender_backend/services/norm_service/mineru_standard_bundle.py`
  - Deterministic helper module for bundle assembly, metrics, cleanup, and comparison.
- `backend/tests/unit/test_mineru_standard_bundle.py`
  - Unit coverage for bundle creation, metrics, TOC cleanup, year-code cleanup, and anchor backfill.
- `backend/tests/smoke/test_mineru_standard_bundle_cli.py`
  - Subprocess-level smoke coverage for `evaluate`, `clean`, and `compare`.
- `docs/skills/mineru-standard-bundle/SKILL.md`
  - Repo-local draft skill document.
- `docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py`
  - CLI entrypoint exposing `evaluate`, `clean`, and `compare`.

**Modify:**

- `backend/tests/unit/_mineru_fixtures.py`
  - Add any tiny helper builders needed by the new tests only if inline fixtures become too repetitive.

**Reference:**

- `docs/superpowers/specs/2026-04-21-mineru-standard-bundle-skill-design.md`
- `backend/tender_backend/services/parse_service/mineru_normalizer.py`
- `backend/tender_backend/services/norm_service/norm_processor.py`
- `backend/tender_backend/services/norm_service/document_assets.py`

---

### Task 1: Create the Core Bundle Helper Module

**Files:**
- Create: `backend/tender_backend/services/norm_service/mineru_standard_bundle.py`
- Create: `backend/tests/unit/test_mineru_standard_bundle.py`

- [ ] **Step 1: Write the failing unit tests for canonical bundle assembly and evaluation**

Create `backend/tests/unit/test_mineru_standard_bundle.py` with these initial tests:

```python
from __future__ import annotations

import json
from pathlib import Path

from tender_backend.services.norm_service.mineru_standard_bundle import (
    StandardSampleInput,
    build_standard_bundle,
    evaluate_standard_bundle,
)


def _write_sample_files(tmp_path: Path, *, md_text: str, middle_json: dict) -> StandardSampleInput:
    pdf_path = tmp_path / "sample.pdf"
    md_path = tmp_path / "sample.md"
    json_path = tmp_path / "sample.json"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")
    md_path.write_text(md_text, encoding="utf-8")
    json_path.write_text(json.dumps(middle_json, ensure_ascii=False), encoding="utf-8")
    return StandardSampleInput(
        name="GB50150-2016",
        pdf_path=pdf_path,
        md_path=md_path,
        json_path=json_path,
    )


def test_build_standard_bundle_returns_parse_asset_like_shape(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        md_text="1 总则\n正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "正文内容", "type": "text"}]}]},
                    ],
                }
            ],
        },
    )

    bundle = build_standard_bundle(sample)

    assert bundle["source_files"]["pdf"] == str(sample.pdf_path)
    assert bundle["document"]["parser_name"] == "mineru"
    assert bundle["document"]["raw_payload"]["pages"][0]["page_number"] == 1
    assert bundle["sections"][0]["title"] == "总则"
    assert bundle["tables"] == []


def test_build_standard_bundle_rejects_unsupported_backend(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        md_text="1 总则\n正文内容",
        middle_json={
            "_backend": "pipeline",
            "_version_name": "2.7.6",
            "pdf_info": [],
        },
    )

    try:
        build_standard_bundle(sample)
    except ValueError as exc:
        assert "Unsupported MinerU backend" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_evaluate_standard_bundle_reports_core_metrics(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        md_text="2016 北京\n\n目次\n1 总则 (1)\n\n1 总则\n1.0.1 正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "text", "lines": [{"spans": [{"content": "2016 北京", "type": "text"}]}]},
                        {"type": "title", "lines": [{"spans": [{"content": "目次", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "1 总则 (1)", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 1,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "1.0.1 正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    summary = evaluate_standard_bundle(bundle)

    assert summary["pdf_pages"] == 2
    assert summary["canonical_pages"] == 2
    assert summary["toc_noise_count"] >= 1
    assert summary["suspicious_section_code_count"] >= 1
    assert summary["section_page_coverage_ratio"] <= 1.0
```

- [ ] **Step 2: Run the new unit test file to verify it fails**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_standard_bundle.py -q
```

Expected: FAIL because `mineru_standard_bundle.py` does not exist.

- [ ] **Step 3: Write the minimal helper module**

Create `backend/tender_backend/services/norm_service/mineru_standard_bundle.py` with this initial structure:

```python
from __future__ import annotations

import json
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
    document_id = uuid5(NAMESPACE_URL, f"file://{sample.pdf_path}")
    sections = _mineru_to_sections(normalized["full_markdown"], normalized["pages"])
    section_rows = [
        {**section, "id": uuid5(NAMESPACE_URL, f"{document_id}:section:{index}")}
        for index, section in enumerate(sections)
    ]
    table_rows = [
        {
            "id": uuid5(NAMESPACE_URL, f"{document_id}:table:{index}"),
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
        "source_files": {
            "pdf": str(sample.pdf_path),
            "md": str(sample.md_path),
            "json": str(sample.json_path),
        },
        "document": serialized,
        "sections": [{**row, "id": str(row["id"])} for row in section_rows],
        "tables": [{**row, "id": str(row["id"])} for row in table_rows],
    }
```

Add the minimal metric helpers to the same file:

```python
def evaluate_standard_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    raw_payload = bundle["document"]["raw_payload"]
    sections = bundle["sections"]
    pdf_pages = len(json.loads(Path(bundle["source_files"]["json"]).read_text(encoding="utf-8")).get("pdf_info") or [])
    sections_with_page = sum(1 for section in sections if section.get("page_start") is not None)
    empty_text_sections = sum(1 for section in sections if not str(section.get("text") or "").strip())
    toc_noise_count = sum(1 for section in sections if _looks_like_toc_noise(section))
    suspicious_section_code_count = sum(1 for section in sections if _looks_like_suspicious_year_code(section))
    return {
        "name": Path(bundle["source_files"]["pdf"]).stem,
        "pdf_pages": pdf_pages,
        "canonical_pages": len(raw_payload.get("pages") or []),
        "page_coverage_ratio": len(raw_payload.get("pages") or []) / max(pdf_pages, 1),
        "tables": len(bundle["tables"]),
        "sections": len(sections),
        "sections_with_page": sections_with_page,
        "section_page_coverage_ratio": sections_with_page / max(len(sections), 1),
        "empty_text_sections": empty_text_sections,
        "toc_noise_count": toc_noise_count,
        "front_matter_noise_count": 0,
        "suspicious_section_code_count": suspicious_section_code_count,
        "backfilled_anchor_count": 0,
        "clause_like_lines": 0,
        "clause_like_unique": 0,
    }
```

```python
def _looks_like_toc_noise(section: dict[str, Any]) -> bool:
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    raw_json = section.get("raw_json") or {}
    markdown = str(raw_json.get("markdown") or "")
    return (
        not text
        and bool(title)
        and ("目次" in markdown or "Contents" in markdown or title.endswith(")"))
    )


def _looks_like_suspicious_year_code(section: dict[str, Any]) -> bool:
    code = str(section.get("section_code") or "").strip()
    raw_json = section.get("raw_json") or {}
    markdown = str(raw_json.get("markdown") or "")
    return code.isdigit() and len(code) == 4 and "中国计划出版社" in markdown
```

- [ ] **Step 4: Run the new unit tests to verify they pass**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_standard_bundle.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/mineru_standard_bundle.py \
  backend/tests/unit/test_mineru_standard_bundle.py
git commit -m "feat: add MinerU standard bundle helpers"
```

### Task 2: Add Deterministic Cleanup Rules

**Files:**
- Modify: `backend/tender_backend/services/norm_service/mineru_standard_bundle.py`
- Modify: `backend/tests/unit/test_mineru_standard_bundle.py`

- [ ] **Step 1: Write the failing cleanup tests**

Extend `backend/tests/unit/test_mineru_standard_bundle.py` with these tests:

```python
from tender_backend.services.norm_service.mineru_standard_bundle import (
    clean_standard_bundle,
    evaluate_standard_bundle,
)


def test_clean_standard_bundle_removes_toc_sections(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        md_text="目次\n1 总则 (1)\n\n1 总则\n1.0.1 正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "目次", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "1 总则 (1)", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 1,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "1.0.1 正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    cleaned = clean_standard_bundle(build_standard_bundle(sample))
    cleaned_titles = [section["title"] for section in cleaned["sections"]]

    assert "总则 (1)" not in cleaned_titles
    assert "总则" in cleaned_titles


def test_clean_standard_bundle_drops_suspicious_year_section_code(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        md_text="2016 北京\n\n1 总则\n1.0.1 正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "text", "lines": [{"spans": [{"content": "中国计划出版社", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "2016 北京", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 1,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "1.0.1 正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    cleaned = clean_standard_bundle(build_standard_bundle(sample))

    assert all(section.get("section_code") != "2016" for section in cleaned["sections"])


def test_clean_standard_bundle_backfills_unique_page_anchor(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        md_text="前言\n\n1 总则\n1.0.1 正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "前言", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 1,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "1.0.1 正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    for section in bundle["sections"]:
        if section.get("section_code") == "1":
            section["page_start"] = None
            section["page_end"] = None
            section["raw_json"] = None
    cleaned = clean_standard_bundle(bundle)
    chapter = next(section for section in cleaned["sections"] if section.get("section_code") == "1")

    assert chapter["page_start"] == 2
    assert chapter["page_end"] == 2
    assert chapter["raw_json"]["page_number"] == 2
```

- [ ] **Step 2: Run the cleanup tests to verify they fail**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_standard_bundle.py -q -k "clean_standard_bundle"
```

Expected: FAIL because `clean_standard_bundle()` does not exist yet.

- [ ] **Step 3: Implement the cleanup helpers**

Add these functions to `backend/tender_backend/services/norm_service/mineru_standard_bundle.py`:

```python
from copy import deepcopy
import re

_TOC_PAGE_MARKERS = ("目次", "Contents")
_TOC_TITLE_RE = re.compile(r"\(\d+\)\s*$")


def clean_standard_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(bundle)
    cleaned["sections"] = _clean_sections(cleaned["sections"], cleaned["document"]["raw_payload"]["pages"])
    cleaned["document"]["raw_payload"]["pages"] = cleaned["document"]["raw_payload"]["pages"]
    return cleaned


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
        cleaned.append(repaired)
    return cleaned


def _looks_like_front_matter_heading_noise(section: dict[str, Any]) -> bool:
    title = str(section.get("title") or "").strip()
    text = str(section.get("text") or "").strip()
    return not text and title in {"中华人民共和国国家标准", "目次", "Contents"}


def _backfill_section_anchor(section: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    if section.get("page_start") is not None:
        return section
    heading = " ".join(part for part in [section.get("section_code"), section.get("title")] if part).strip()
    matches = [page for page in pages if heading and heading in str(page.get("markdown") or "")]
    if len(matches) != 1:
        return section
    matched = matches[0]
    return {
        **section,
        "page_start": matched["page_number"],
        "page_end": matched["page_number"],
        "raw_json": {
            "page_number": matched["page_number"],
            "markdown": matched["markdown"],
        },
    }
```

Update `evaluate_standard_bundle()` so it recomputes `front_matter_noise_count` and `backfilled_anchor_count`:

```python
front_matter_noise_count = sum(1 for section in sections if _looks_like_front_matter_heading_noise(section))
backfilled_anchor_count = sum(
    1
    for section in sections
    if section.get("page_start") is not None and section.get("raw_json") is not None
)
```

- [ ] **Step 4: Re-run the cleanup tests to verify they pass**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_standard_bundle.py -q -k "clean_standard_bundle"
```

Expected: PASS.

- [ ] **Step 5: Run the full unit file to verify there is no regression**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_standard_bundle.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/norm_service/mineru_standard_bundle.py \
  backend/tests/unit/test_mineru_standard_bundle.py
git commit -m "feat: add deterministic MinerU bundle cleanup"
```

### Task 3: Add Compare Helpers and Output Writers

**Files:**
- Modify: `backend/tender_backend/services/norm_service/mineru_standard_bundle.py`
- Modify: `backend/tests/unit/test_mineru_standard_bundle.py`

- [ ] **Step 1: Write the failing comparison tests**

Add these tests:

```python
from tender_backend.services.norm_service.mineru_standard_bundle import (
    compare_standard_summaries,
    write_bundle_outputs,
)


def test_compare_standard_summaries_orders_samples_and_preserves_metrics() -> None:
    comparison = compare_standard_summaries(
        [
            {"name": "GB50150-2016", "toc_noise_count": 5, "section_page_coverage_ratio": 0.8},
            {"name": "GB50147-2010", "toc_noise_count": 2, "section_page_coverage_ratio": 0.9},
        ]
    )

    assert [row["name"] for row in comparison["samples"]] == ["GB50147-2010", "GB50150-2016"]
    assert comparison["samples"][0]["toc_noise_count"] == 2


def test_write_bundle_outputs_emits_expected_files(tmp_path: Path) -> None:
    bundle = {
        "source_files": {"pdf": "/tmp/spec.pdf", "md": "/tmp/spec.md", "json": "/tmp/spec.json"},
        "document": {"raw_payload": {"pages": [], "tables": [], "full_markdown": "", "parser_version": "2.7.6"}},
        "sections": [],
        "tables": [],
    }
    summary = {"name": "GB50150-2016", "sections": 0}

    paths = write_bundle_outputs(tmp_path, bundle=bundle, summary=summary)

    assert sorted(path.name for path in paths) == [
        "raw-payload.json",
        "summary.json",
        "system-bundle.json",
    ]
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_standard_bundle.py -q -k "compare_standard_summaries or write_bundle_outputs"
```

Expected: FAIL because the helpers do not exist yet.

- [ ] **Step 3: Implement compare and write helpers**

Add these functions:

```python
def compare_standard_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(summaries, key=lambda item: str(item.get("name") or ""))
    return {
        "sample_count": len(ordered),
        "samples": ordered,
    }


def write_bundle_outputs(output_dir: Path, *, bundle: dict[str, Any], summary: dict[str, Any]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_payload_path = output_dir / "raw-payload.json"
    system_bundle_path = output_dir / "system-bundle.json"
    summary_path = output_dir / "summary.json"
    raw_payload_path.write_text(
        json.dumps(bundle["document"]["raw_payload"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    system_bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return [raw_payload_path, summary_path, system_bundle_path]
```

Also add a Markdown compare report helper:

```python
def write_compare_report(output_dir: Path, comparison: dict[str, Any]) -> Path:
    report_path = output_dir / "compare-report.md"
    lines = ["# MinerU Standard Bundle Comparison", ""]
    for sample in comparison["samples"]:
        lines.append(f"- `{sample['name']}`: toc_noise={sample['toc_noise_count']}, anchor_ratio={sample['section_page_coverage_ratio']}")
    report_path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    return report_path
```

- [ ] **Step 4: Re-run the targeted tests to verify they pass**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_standard_bundle.py -q -k "compare_standard_summaries or write_bundle_outputs"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/mineru_standard_bundle.py \
  backend/tests/unit/test_mineru_standard_bundle.py
git commit -m "feat: add MinerU bundle compare outputs"
```

### Task 4: Add the CLI Entry Point and Smoke Tests

**Files:**
- Create: `docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py`
- Create: `backend/tests/smoke/test_mineru_standard_bundle_cli.py`

- [ ] **Step 1: Write the failing smoke tests for `evaluate`, `clean`, and `compare`**

Create `backend/tests/smoke/test_mineru_standard_bundle_cli.py` with these tests:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _write_sample(tmp_path: Path, *, name: str) -> tuple[Path, Path, Path]:
    pdf_path = tmp_path / f"{name}.pdf"
    md_path = tmp_path / f"{name}.md"
    json_path = tmp_path / f"{name}.json"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")
    md_path.write_text("1 总则\\n1.0.1 正文内容", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "_backend": "hybrid",
                "_version_name": "2.7.6",
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "para_blocks": [
                            {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                            {"type": "text", "lines": [{"spans": [{"content": "1.0.1 正文内容", "type": "text"}]}]},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pdf_path, md_path, json_path


def test_cli_evaluate_writes_base_outputs(tmp_path: Path) -> None:
    pdf_path, md_path, json_path = _write_sample(tmp_path, name="gb50150")
    output_dir = tmp_path / "out"
    result = subprocess.run(
        [
            "./.venv/bin/python",
            "docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py",
            "evaluate",
            "--name",
            "GB50150-2016",
            "--pdf",
            str(pdf_path),
            "--md",
            str(md_path),
            "--json",
            str(json_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd="/Users/palmtom/Projects/tender",
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "raw-payload.json").exists()
    assert (output_dir / "system-bundle.json").exists()
    assert (output_dir / "summary.json").exists()


def test_cli_clean_writes_cleaned_outputs(tmp_path: Path) -> None:
    pdf_path, md_path, json_path = _write_sample(tmp_path, name="gb50150")
    output_dir = tmp_path / "out"
    subprocess.run(
        [
            "./.venv/bin/python",
            "docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py",
            "clean",
            "--name",
            "GB50150-2016",
            "--pdf",
            str(pdf_path),
            "--md",
            str(md_path),
            "--json",
            str(json_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd="/Users/palmtom/Projects/tender",
        check=True,
        capture_output=True,
        text=True,
    )

    assert (output_dir / "cleaned-system-bundle.json").exists()
    assert (output_dir / "cleaned-summary.json").exists()


def test_cli_compare_writes_json_and_markdown_reports(tmp_path: Path) -> None:
    left = _write_sample(tmp_path / "left", name="gb50147")
    right = _write_sample(tmp_path / "right", name="gb50150")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {"name": "GB50147-2010", "pdf": str(left[0]), "md": str(left[1]), "json": str(left[2])},
                {"name": "GB50150-2016", "pdf": str(right[0]), "md": str(right[1]), "json": str(right[2])},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "compare"
    result = subprocess.run(
        [
            "./.venv/bin/python",
            "docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py",
            "compare",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd="/Users/palmtom/Projects/tender",
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "compare-summary.json").exists()
    assert (output_dir / "compare-report.md").exists()
```

- [ ] **Step 2: Run the smoke test file to verify it fails**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/smoke/test_mineru_standard_bundle_cli.py -q
```

Expected: FAIL because the CLI script does not exist.

- [ ] **Step 3: Write the CLI entrypoint**

Create `docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))

from tender_backend.services.norm_service.mineru_standard_bundle import (
    StandardSampleInput,
    build_standard_bundle,
    clean_standard_bundle,
    compare_standard_summaries,
    evaluate_standard_bundle,
    write_bundle_outputs,
    write_compare_report,
)


def _sample_from_args(args: argparse.Namespace) -> StandardSampleInput:
    return StandardSampleInput(
        name=args.name,
        pdf_path=Path(args.pdf),
        md_path=Path(args.md),
        json_path=Path(args.json),
    )


def cmd_evaluate(args: argparse.Namespace) -> int:
    sample = _sample_from_args(args)
    bundle = build_standard_bundle(sample)
    summary = evaluate_standard_bundle(bundle)
    write_bundle_outputs(Path(args.output_dir), bundle=bundle, summary=summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    sample = _sample_from_args(args)
    bundle = build_standard_bundle(sample)
    cleaned = clean_standard_bundle(bundle)
    cleaned_summary = evaluate_standard_bundle(cleaned)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cleaned-system-bundle.json").write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "cleaned-summary.json").write_text(json.dumps(cleaned_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(cleaned_summary, ensure_ascii=False, indent=2))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    summaries = []
    for item in manifest:
        sample = StandardSampleInput(
            name=item["name"],
            pdf_path=Path(item["pdf"]),
            md_path=Path(item["md"]),
            json_path=Path(item["json"]),
        )
        bundle = build_standard_bundle(sample)
        summaries.append(evaluate_standard_bundle(bundle))
    comparison = compare_standard_summaries(summaries)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "compare-summary.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    write_compare_report(output_dir, comparison)
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--name", required=True)
    evaluate.add_argument("--pdf", required=True)
    evaluate.add_argument("--md", required=True)
    evaluate.add_argument("--json", required=True)
    evaluate.add_argument("--output-dir", required=True)
    evaluate.set_defaults(func=cmd_evaluate)
    clean = subparsers.add_parser("clean")
    clean.add_argument("--name", required=True)
    clean.add_argument("--pdf", required=True)
    clean.add_argument("--md", required=True)
    clean.add_argument("--json", required=True)
    clean.add_argument("--output-dir", required=True)
    clean.set_defaults(func=cmd_clean)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--manifest", required=True)
    compare.add_argument("--output-dir", required=True)
    compare.set_defaults(func=cmd_compare)
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))
```

- [ ] **Step 4: Re-run the smoke tests to verify they pass**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/smoke/test_mineru_standard_bundle_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py \
  backend/tests/smoke/test_mineru_standard_bundle_cli.py
git commit -m "feat: add MinerU standard bundle CLI"
```

### Task 5: Add the Repo-Local Draft Skill Document

**Files:**
- Create: `docs/skills/mineru-standard-bundle/SKILL.md`

- [ ] **Step 1: Write the draft `SKILL.md`**

Create `docs/skills/mineru-standard-bundle/SKILL.md`:

```markdown
---
name: mineru-standard-bundle
description: Use when working in the tender repository with MinerU 2.7.x hybrid/vlm standard-document outputs and you need deterministic bundle generation, quality evaluation, cleanup, or cross-standard comparison from local pdf, md, and json files.
---

# MinerU Standard Bundle

Use this skill for repo-local standard-document workflows that start from local MinerU files:

- `pdf`
- `md`
- `json`

This skill is specific to:

- the `tender` repository;
- MinerU `2.7.x`;
- `hybrid` and `vlm` backends only;
- standard documents, not tender-file ingestion.

Do not use this skill for:

- legacy `pipeline` payloads;
- arbitrary OCR formats;
- database import execution.

## Workflow

1. Confirm the input files are local and belong to the same document.
2. Run the CLI `evaluate` command to emit `raw-payload.json`, `system-bundle.json`, and `summary.json`.
3. Run `clean` when you need to reduce TOC noise, suspicious year-like section codes, and recoverable missing page anchors.
4. Run `compare` with a manifest when you need the same metrics across multiple standards.

## Commands

Single-document evaluation:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py evaluate \
  --name GB50150-2016 \
  --pdf /abs/path/50150.pdf \
  --md /abs/path/GB_50150.md \
  --json /abs/path/GB\ 50150.json \
  --output-dir tmp/mineru_standard_bundle/GB50150-2016
```

Deterministic cleanup:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py clean \
  --name GB50150-2016 \
  --pdf /abs/path/50150.pdf \
  --md /abs/path/GB_50150.md \
  --json /abs/path/GB\ 50150.json \
  --output-dir tmp/mineru_standard_bundle/GB50150-2016
```

Cross-standard comparison:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py compare \
  --manifest /abs/path/compare-manifest.json \
  --output-dir tmp/mineru_standard_bundle/compare
```

## Output Files

- `raw-payload.json`
- `system-bundle.json`
- `summary.json`
- `cleaned-system-bundle.json`
- `cleaned-summary.json`
- `compare-summary.json`
- `compare-report.md`

## Review Focus

After running the workflow, review:

- `page_coverage_ratio`
- `section_page_coverage_ratio`
- `toc_noise_count`
- `suspicious_section_code_count`
```

- [ ] **Step 2: Verify the skill reads cleanly and stays within the approved scope**

Check that the draft skill:

- mentions `tender` repo specificity;
- limits itself to `hybrid/vlm`;
- includes `evaluate`, `clean`, and `compare`;
- excludes DB import execution.

- [ ] **Step 3: Commit**

```bash
git add docs/skills/mineru-standard-bundle/SKILL.md
git commit -m "docs: add MinerU standard bundle skill draft"
```

### Task 6: Run Real-Sample Verification for GB50147 and GB50150

**Files:**
- Use: `docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py`
- Use: local sample files in `/Users/palmtom/Downloads/`

- [ ] **Step 1: Run `evaluate` for `GB50147-2010`**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py evaluate \
  --name GB50147-2010 \
  --pdf "/Users/palmtom/Downloads/GB 50147-2010.pdf" \
  --md "/Users/palmtom/Downloads/MinerU_markdown_GB50147_2010_电气装置安装工程_高压电器施工及验收规范_2045474865843142656.md" \
  --json "/Users/palmtom/Downloads/MinerU_GB50147 2010 电气装置安装工程 高压电器施工及验收规范__20260418120949.json" \
  --output-dir tmp/mineru_standard_bundle/GB50147-2010
```

Expected: exit `0` and write base outputs.

- [ ] **Step 2: Run `evaluate` for `GB50150-2016`**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py evaluate \
  --name GB50150-2016 \
  --pdf "/Users/palmtom/Downloads/50150.pdf" \
  --md "/Users/palmtom/Downloads/GB_50150.md" \
  --json "/Users/palmtom/Downloads/GB 50150.json" \
  --output-dir tmp/mineru_standard_bundle/GB50150-2016
```

Expected: exit `0` and write base outputs.

- [ ] **Step 3: Run `clean` for `GB50150-2016`**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py clean \
  --name GB50150-2016 \
  --pdf "/Users/palmtom/Downloads/50150.pdf" \
  --md "/Users/palmtom/Downloads/GB_50150.md" \
  --json "/Users/palmtom/Downloads/GB 50150.json" \
  --output-dir tmp/mineru_standard_bundle/GB50150-2016
```

Expected: exit `0` and write cleaned outputs.

- [ ] **Step 4: Run `compare` for `GB50147-2010` and `GB50150-2016`**

Create `tmp/mineru_standard_bundle/compare-manifest.json`:

```json
[
  {
    "name": "GB50147-2010",
    "pdf": "/Users/palmtom/Downloads/GB 50147-2010.pdf",
    "md": "/Users/palmtom/Downloads/MinerU_markdown_GB50147_2010_电气装置安装工程_高压电器施工及验收规范_2045474865843142656.md",
    "json": "/Users/palmtom/Downloads/MinerU_GB50147 2010 电气装置安装工程 高压电器施工及验收规范__20260418120949.json"
  },
  {
    "name": "GB50150-2016",
    "pdf": "/Users/palmtom/Downloads/50150.pdf",
    "md": "/Users/palmtom/Downloads/GB_50150.md",
    "json": "/Users/palmtom/Downloads/GB 50150.json"
  }
]
```

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py compare \
  --manifest tmp/mineru_standard_bundle/compare-manifest.json \
  --output-dir tmp/mineru_standard_bundle/compare
```

Expected: exit `0` and write `compare-summary.json` plus `compare-report.md`.

- [ ] **Step 5: Verify the cleaned `GB50150-2016` metrics improved in the intended direction**

Check `tmp/mineru_standard_bundle/GB50150-2016/summary.json` and `tmp/mineru_standard_bundle/GB50150-2016/cleaned-summary.json` and confirm:

```text
cleaned.toc_noise_count < raw.toc_noise_count
cleaned.suspicious_section_code_count < raw.suspicious_section_code_count
cleaned.section_page_coverage_ratio >= raw.section_page_coverage_ratio
cleaned.page_coverage_ratio == raw.page_coverage_ratio
```

- [ ] **Step 6: Run the full targeted verification slice**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest \
  backend/tests/unit/test_mineru_standard_bundle.py \
  backend/tests/smoke/test_mineru_standard_bundle_cli.py \
  backend/tests/unit/test_mineru_normalizer.py \
  backend/tests/unit/test_document_assets.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/skills/mineru-standard-bundle \
  backend/tender_backend/services/norm_service/mineru_standard_bundle.py \
  backend/tests/unit/test_mineru_standard_bundle.py \
  backend/tests/smoke/test_mineru_standard_bundle_cli.py
git commit -m "feat: add MinerU standard bundle draft skill"
```

## Self-Review

- Spec coverage:
  - repo-local draft skill: covered in Task 5
  - single script with `evaluate/clean/compare`: covered in Task 4
  - deterministic cleanup only: covered in Task 2
  - cross-standard comparison: covered in Task 3 and Task 6
  - real-sample verification on `GB50147` and `GB50150`: covered in Task 6
- Placeholder scan:
  - no `TBD`, `TODO`, or “implement later” markers remain
  - all code-changing tasks include explicit code blocks
  - all verification steps include exact commands and expected outcomes
- Type consistency:
  - `StandardSampleInput`, `build_standard_bundle`, `evaluate_standard_bundle`, `clean_standard_bundle`, `compare_standard_summaries`, and `write_bundle_outputs` are defined once and reused consistently across tasks

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-mineru-standard-bundle-skill.md`.

Execution mode already chosen: **Subagent-Driven (recommended)**.

Next step: use `superpowers:subagent-driven-development` to execute the plan task-by-task with review between tasks.
