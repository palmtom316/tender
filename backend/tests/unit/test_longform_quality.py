from tender_backend.services.longform_quality import (
    build_chart_closure_report,
    build_coverage_report,
    build_page_gate,
    estimate_markdown_pages,
)


def test_estimate_markdown_pages_counts_chinese_text_tables_charts_and_breaks():
    content = (
        "# 8 技术方案\n"
        + ("施工组织。" * 900)
        + "\n{{chart:risk_matrix}}\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        + "<div style='page-break-after: always'></div>"
    )

    estimate = estimate_markdown_pages(content, target_pages=100)

    assert estimate["target_pages"] == 100
    assert estimate["estimated_pages"] >= 12
    assert estimate["evidence"]["chart_count"] == 1
    assert estimate["evidence"]["table_row_count"] == 2
    assert estimate["evidence"]["explicit_page_break_count"] == 1


def test_page_gate_blocks_below_ninety_percent_target():
    gate = build_page_gate(target_pages=100, estimated_pages=88, actual_pages=None, actual_status="unchecked")

    assert gate["page_count_passed"] is False
    assert gate["page_count_status"] == "failed_estimate_below_minimum"
    assert gate["minimum_required_pages"] == 90


def test_page_gate_blocks_unchecked_when_estimate_is_not_enough():
    gate = build_page_gate(target_pages=100, estimated_pages=95, actual_pages=None, actual_status="unchecked")

    assert gate["page_count_passed"] is False
    assert gate["page_count_status"] == "warning_actual_unchecked"
    assert "未校验" in gate["page_count_message"]


def test_page_gate_passes_when_actual_pages_meet_minimum():
    gate = build_page_gate(target_pages=100, estimated_pages=92, actual_pages=91, actual_status="counted")

    assert gate["page_count_passed"] is True
    assert gate["page_count_status"] == "passed"


def test_coverage_report_blocks_missing_8x_section_and_hard_constraint_gap():
    content = "## 8.1 编制依据\n" + ("响应内容。" * 80)
    checklist = [
        {"section_code": "8.1", "title": "编制依据", "min_chars": 100, "required_charts": [], "required_tables": []},
        {"section_code": "8.2", "title": "施工组织", "min_chars": 100, "required_charts": ["org_chart"], "required_tables": []},
    ]
    constraints = [{"id": "c1", "title": "项目经理到岗", "confirmation_level": "critical", "response_section_code": "8.2"}]

    report = build_coverage_report(content, checklist=checklist, constraints=constraints)

    assert report["coverage_passed"] is False
    issue_codes = {issue["code"] for issue in report["issues"]}
    assert "missing_section" in issue_codes
    assert "missing_required_chart" in issue_codes
    assert "hard_constraint_uncovered" in issue_codes


def test_chart_closure_report_reconciles_references_assets_and_docx_insertions():
    report = build_chart_closure_report(
        content_md="正文 {{chart:risk_matrix}} 和 {{chart:schedule}}",
        chart_assets=[
            {"placeholder_key": "risk_matrix", "status": "approved", "rendered_path": "/tmp/risk.png"},
            {"placeholder_key": "schedule", "status": "draft", "rendered_path": None},
        ],
        inserted_chart_keys=["risk_matrix"],
        residual_placeholders=["schedule"],
    )

    assert report["chart_closure_passed"] is False
    assert report["referenced_chart_count"] == 2
    assert report["approved_chart_count"] == 1
    assert report["inserted_chart_count"] == 1
    assert {issue["chart_key"] for issue in report["issues"]} == {"schedule"}


def test_coverage_report_requires_charts_in_the_declared_section_body():
    content = "\n".join(
        [
            "## 8.1 编制依据",
            "{{chart:org_chart}}",
            "## 8.2 施工组织",
            "施工组织内容充分。",
        ]
    )
    checklist = [
        {"section_code": "8.2", "title": "施工组织", "min_chars": 1, "required_charts": ["org_chart"], "required_tables": []},
    ]

    report = build_coverage_report(content, checklist=checklist, constraints=[])

    assert report["coverage_passed"] is False
    assert any(
        issue["code"] == "missing_required_chart"
        and issue["section_code"] == "8.2"
        and issue["chart_key"] == "org_chart"
        for issue in report["issues"]
    )


def test_chart_closure_report_blocks_residual_placeholder_absent_from_source_content():
    report = build_chart_closure_report(
        content_md="正文 {{chart:risk_matrix}}",
        chart_assets=[{"placeholder_key": "risk_matrix", "status": "approved", "rendered_path": "/tmp/risk.png"}],
        inserted_chart_keys=["risk_matrix"],
        residual_placeholders=["stale_docx_placeholder"],
    )

    assert report["chart_closure_passed"] is False
    assert report["residual_placeholder_count"] == 1
    assert any(
        issue["code"] == "chart_placeholder_residual" and issue["chart_key"] == "stale_docx_placeholder"
        for issue in report["issues"]
    )
