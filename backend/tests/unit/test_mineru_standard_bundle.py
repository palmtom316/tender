from __future__ import annotations

import json
from pathlib import Path

from tender_backend.services.norm_service.mineru_standard_bundle import (
    StandardSampleInput,
    build_standard_bundle,
    clean_standard_bundle,
    compare_standard_summaries,
    evaluate_standard_bundle,
    write_bundle_outputs,
)


def _write_sample_files(tmp_path: Path, *, name: str, md_text: str, middle_json: dict) -> StandardSampleInput:
    tmp_path.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / f"{name}.pdf"
    md_path = tmp_path / f"{name}.md"
    json_path = tmp_path / f"{name}.json"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")
    md_path.write_text(md_text, encoding="utf-8")
    json_path.write_text(json.dumps(middle_json, ensure_ascii=False), encoding="utf-8")
    return StandardSampleInput(
        name=name,
        pdf_path=pdf_path,
        md_path=md_path,
        json_path=json_path,
    )


def test_build_standard_bundle_returns_parse_asset_like_shape(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50150-2016",
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

    assert bundle["name"] == "GB50150-2016"
    assert bundle["source_files"]["pdf"] == str(sample.pdf_path)
    assert bundle["document"]["parser_name"] == "mineru"
    assert bundle["document"]["raw_payload"]["pages"][0]["page_number"] == 1
    assert bundle["sections"][0]["title"] == "总则"
    assert bundle["tables"] == []


def test_build_standard_bundle_rejects_unsupported_backend(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50150-2016",
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
        name="GB50150-2016",
        md_text="2016 北京\n\n目次\n1 总则 (1)\n\n1 总则\n1.0.1 正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "text", "lines": [{"spans": [{"content": "中国计划出版社", "type": "text"}]}]},
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
    assert summary["clause_like_lines"] >= 1


def test_clean_standard_bundle_removes_toc_sections(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50150-2016",
        md_text="目次\n1 总则 (1)\n\n1 总则\n这是正文内容",
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
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
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
        name="GB50150-2016",
        md_text="2016 北京\n\n1 总则\n这是正文内容",
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
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
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
        name="GB50150-2016",
        md_text="前言\n\n1 总则\n这是正文内容",
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
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
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


def test_clean_standard_bundle_backfills_title_only_anchor_with_normalized_match(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50148-2010",
        md_text="前言\n\n1 总 则\n这是正文内容",
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
                        {"type": "title", "lines": [{"spans": [{"content": "1 总 则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    for section in bundle["sections"]:
        if section.get("section_code") == "1":
            section["section_code"] = None
            section["title"] = "1 总则"
            section["page_start"] = None
            section["page_end"] = None
            section["raw_json"] = None

    cleaned = clean_standard_bundle(bundle)
    chapter = next(section for section in cleaned["sections"] if section.get("title") == "1 总则")

    assert chapter["page_start"] == 2
    assert chapter["page_end"] == 2
    assert chapter["raw_json"]["page_number"] == 2


def test_clean_standard_bundle_drops_empty_publication_heading_noise(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50148-2010",
        md_text="关于发布国家标准\n\n1 总则\n这是正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "关于发布国家标准", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 1,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    cleaned = clean_standard_bundle(build_standard_bundle(sample))

    assert all(section.get("title") != "关于发布国家标准" for section in cleaned["sections"])


def test_clean_standard_bundle_drops_unanchored_empty_heading_noise(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50150-2016",
        md_text="1 总则\n这是正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    bundle["sections"].append(
        {
            "id": "noise-heading",
            "section_code": None,
            "title": "4.2 安装与调整",
            "level": 2,
            "page_start": None,
            "page_end": None,
            "text": "",
            "text_source": "mineru_markdown",
            "sort_order": 99,
            "raw_json": None,
        }
    )

    cleaned = clean_standard_bundle(bundle)

    assert all(section.get("id") != "noise-heading" for section in cleaned["sections"])


def test_clean_standard_bundle_keeps_unanchored_appendix_with_table_text(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50150-2016",
        md_text="1 总则\n这是正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    bundle["sections"].append(
        {
            "id": "appendix-table",
            "section_code": None,
            "title": "附录A 特殊试验项目",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "表 A 特殊试验项目\n\n<table><tr><td>序号</td></tr></table>",
            "text_source": "mineru_markdown",
            "sort_order": 100,
            "raw_json": None,
        }
    )

    cleaned = clean_standard_bundle(bundle)

    assert any(section.get("id") == "appendix-table" for section in cleaned["sections"])


def test_clean_standard_bundle_drops_unanchored_empty_book_title_heading(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50147-2010",
        md_text="1 总则\n这是正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    bundle["sections"].append(
        {
            "id": "book-title-noise",
            "section_code": None,
            "title": "电气装置安装工程高压电器施工及验收规范",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "",
            "text_source": "mineru_markdown",
            "sort_order": 101,
            "raw_json": None,
        }
    )

    cleaned = clean_standard_bundle(bundle)

    assert all(section.get("id") != "book-title-noise" for section in cleaned["sections"])


def test_clean_standard_bundle_drops_unanchored_explanation_heading(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50150-2016",
        md_text="1 总则\n这是正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    bundle["sections"].append(
        {
            "id": "wording-note-noise",
            "section_code": None,
            "title": "本规范用词说明",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "",
            "text_source": "mineru_markdown",
            "sort_order": 102,
            "raw_json": None,
        }
    )

    cleaned = clean_standard_bundle(bundle)

    assert all(section.get("id") != "wording-note-noise" for section in cleaned["sections"])


def test_clean_standard_bundle_drops_half_book_title_heading(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50147-2010",
        md_text="1 总则\n这是正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    bundle["sections"].append(
        {
            "id": "half-book-title-noise",
            "section_code": None,
            "title": "电气装置安装工程",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "",
            "text_source": "mineru_markdown",
            "sort_order": 103,
            "raw_json": None,
        }
    )

    cleaned = clean_standard_bundle(bundle)

    assert all(section.get("id") != "half-book-title-noise" for section in cleaned["sections"])


def test_clean_standard_bundle_backfills_compact_heading_to_non_toc_page(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50148-2010",
        md_text="目次\n5 互感器 (35)\n\n5互感器\n5.1 一般规定\n这是正文内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "目次", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "5 互感器 (35)", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 1,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "5互感器", "type": "text"}]}]},
                        {"type": "title", "lines": [{"spans": [{"content": "5.1 一般规定", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    bundle["sections"].append(
        {
            "id": "compact-heading",
            "section_code": None,
            "title": "5互感器",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "",
            "text_source": "mineru_markdown",
            "sort_order": 104,
            "raw_json": None,
        }
    )

    cleaned = clean_standard_bundle(bundle)
    chapter = next(section for section in cleaned["sections"] if section.get("title") == "5互感器")

    assert chapter["page_start"] == 2
    assert chapter["page_end"] == 2
    assert chapter["raw_json"]["page_number"] == 2


def test_clean_standard_bundle_backfills_compact_heading_to_earliest_non_toc_page(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50148-2010",
        md_text="目次\n5 互感器 (35)\n\n5互感器\n5.1 一般规定\n这是正文内容\n\n5 互感器\n5.1 一般规定\n说明页内容",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "目次", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "5 互感器 (35)", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 1,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "5互感器", "type": "text"}]}]},
                        {"type": "title", "lines": [{"spans": [{"content": "5.1 一般规定", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 2,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "5 互感器", "type": "text"}]}]},
                        {"type": "title", "lines": [{"spans": [{"content": "5.1 一般规定", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "说明页内容", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    bundle["sections"].append(
        {
            "id": "compact-heading-duplicate",
            "section_code": None,
            "title": "5互感器",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "",
            "text_source": "mineru_markdown",
            "sort_order": 105,
            "raw_json": None,
        }
    )

    cleaned = clean_standard_bundle(bundle)
    chapter = next(section for section in cleaned["sections"] if section.get("id") == "compact-heading-duplicate")

    assert chapter["page_start"] == 2
    assert chapter["page_end"] == 2
    assert chapter["raw_json"]["page_number"] == 2


def test_clean_standard_bundle_backfills_appendix_to_earliest_non_toc_page(tmp_path: Path) -> None:
    sample = _write_sample_files(
        tmp_path,
        name="GB50150-2016",
        md_text="目次\n附录A 特殊试验项目 (74)\n\n附录A 特殊试验项目\n表 A 特殊试验项目\n\n附录A 特殊试验项目\n(1)条文说明",
        middle_json={
            "_backend": "hybrid",
            "_version_name": "2.7.6",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "目次", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "附录A 特殊试验项目 (74)", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 1,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "附录A 特殊试验项目", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "表 A 特殊试验项目", "type": "text"}]}]},
                    ],
                },
                {
                    "page_idx": 2,
                    "para_blocks": [
                        {"type": "title", "lines": [{"spans": [{"content": "附录A 特殊试验项目", "type": "text"}]}]},
                        {"type": "text", "lines": [{"spans": [{"content": "(1)条文说明", "type": "text"}]}]},
                    ],
                },
            ],
        },
    )

    bundle = build_standard_bundle(sample)
    bundle["sections"].append(
        {
            "id": "appendix-anchor",
            "section_code": None,
            "title": "附录A 特殊试验项目",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "表 A 特殊试验项目\n\n<table><tr><td>序号</td></tr></table>",
            "text_source": "mineru_markdown",
            "sort_order": 106,
            "raw_json": None,
        }
    )

    cleaned = clean_standard_bundle(bundle)
    appendix = next(section for section in cleaned["sections"] if section.get("id") == "appendix-anchor")

    assert appendix["page_start"] == 2
    assert appendix["page_end"] == 2
    assert appendix["raw_json"]["page_number"] == 2


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
    Path("/tmp/spec.json").write_text(json.dumps({"pdf_info": []}), encoding="utf-8")

    paths = write_bundle_outputs(tmp_path, bundle=bundle, summary=summary)

    assert sorted(path.name for path in paths) == [
        "raw-payload.json",
        "summary.json",
        "system-bundle.json",
    ]
