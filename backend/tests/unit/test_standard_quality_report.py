from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from tender_backend.services.norm_service.quality_report import build_standard_quality_report
from tender_backend.services.norm_service.validation import ValidationIssue, ValidationResult


def test_build_standard_quality_report_flags_low_anchor_coverage_and_recommends_skills() -> None:
    document_asset = SimpleNamespace(
        pages=[
            SimpleNamespace(page_number=1, normalized_text="1 总则\n正文"),
            SimpleNamespace(page_number=2, normalized_text="2 术语\n正文"),
        ]
    )
    raw_sections = [
        {"id": "s0", "title": "中华人民共和国国家标准", "text": "", "level": 1},
        {"id": "s1", "section_code": "1", "title": "总则", "text": "正文", "level": 1},
    ]
    normalized_sections = [
        {"id": "s1", "section_code": "1", "title": "总则", "text": "正文", "level": 1},
    ]
    clauses = [
        {
            "id": uuid4(),
            "clause_no": "1.0.1",
            "clause_text": "正文",
            "clause_type": "normative",
            "source_type": "text",
            "page_start": None,
        }
    ]
    validation = ValidationResult(issues=[
        ValidationIssue(
            code="page.missing_anchor",
            severity="warning",
            message="Clause 1.0.1: missing page anchors",
            clause_no="1.0.1",
        )
    ])

    report = build_standard_quality_report(
        document_asset=document_asset,
        raw_sections=raw_sections,
        normalized_sections=normalized_sections,
        tables=[],
        clauses=clauses,
        validation=validation,
        warnings=["Clause 1.0.1: missing page anchors"],
    )

    assert report["overview"]["status"] == "fail"
    assert report["metrics"]["raw_section_count"] == 2
    assert report["metrics"]["section_anchor_coverage"] == 0.0
    assert report["metrics"]["clause_anchor_coverage"] == 0.0
    assert report["metrics"]["front_matter_noise_count"] == 1
    assert report["gates"][0]["code"] == "section_anchor_coverage"
    assert report["gates"][0]["status"] == "fail"
    assert report["recommended_skills"][0]["skill_name"] == "mineru-standard-bundle"
    assert any(skill["skill_name"] == "standard-parse-recovery" for skill in report["recommended_skills"])


def test_build_standard_quality_report_separates_executed_available_and_disabled_skills() -> None:
    document_asset = SimpleNamespace(pages=[SimpleNamespace(page_number=1, normalized_text="1 总则")])
    validation = ValidationResult(issues=[])

    report = build_standard_quality_report(
        document_asset=document_asset,
        raw_sections=[{"id": "s1", "page_start": 1, "title": "1 总则", "text": "正文"}],
        normalized_sections=[{"id": "s1", "page_start": 1, "title": "1 总则", "text": "正文"}],
        tables=[],
        clauses=[
            {
                "id": uuid4(),
                "clause_no": "1.0.1",
                "clause_text": "正文",
                "clause_type": "normative",
                "source_type": "text",
                "page_start": 1,
            }
        ],
        validation=validation,
        executed_skills=[
            {
                "skill_name": "mineru-standard-bundle",
                "hook": "preflight_parse_asset",
                "status": "pass",
                "blocking": False,
                "messages": [],
                "metrics": {"section_page_coverage_ratio": 1.0},
            }
        ],
    )

    assert report["executed_skills"][0]["skill_name"] == "mineru-standard-bundle"
    assert any(skill["skill_name"] == "standard-parse-recovery" for skill in report["available_skills"])
    assert any(skill["skill_name"] == "standard-parse-recovery" for skill in report["disabled_parse_plugins"])
    assert report["recommended_skills"] == []


def test_build_standard_quality_report_fails_when_ai_fallback_ratio_is_high() -> None:
    document_asset = SimpleNamespace(pages=[SimpleNamespace(page_number=1, normalized_text="1 总则")])

    report = build_standard_quality_report(
        document_asset=document_asset,
        raw_sections=[{"id": "s1", "page_start": 1, "title": "1 总则", "text": "正文"}],
        normalized_sections=[{"id": "s1", "page_start": 1, "title": "1 总则", "text": "正文"}],
        tables=[],
        clauses=[
            {
                "id": uuid4(),
                "clause_no": "1.0.1",
                "clause_text": "正文",
                "clause_type": "normative",
                "source_type": "text",
                "page_start": 1,
            }
        ],
        validation=ValidationResult(issues=[]),
        ai_fallback_count=3,
        total_parser_block_count=5,
        max_ai_fallback_ratio=0.2,
    )

    assert report["overview"]["status"] == "fail"
    assert report["metrics"]["ai_fallback_ratio"] == 0.6
    assert any(
        gate["code"] == "ai_fallback_ratio" and gate["status"] == "fail"
        for gate in report["gates"]
    )
