from types import MappingProxyType

from tender_backend.services.longform_quality import (
    build_blind_bid_report,
    build_chart_closure_report,
    build_coverage_report,
    build_page_gate,
    estimate_markdown_pages,
    normalize_allowed_chart_keys,
)


def test_blind_bid_report_detects_configured_terms_and_common_sensitive_patterns() -> None:
    report = build_blind_bid_report(
        "重庆示例电力工程有限责任公司承诺参与渝中片区配网工程，联系人13800000000，日期2026年5月19日。",
        sensitive_terms=["重庆示例电力工程有限责任公司", "渝中片区配网工程"],
        chapter_code="2",
        volume_type="business",
    )

    assert report["blind_check_passed"] is False
    codes = {issue["code"] for issue in report["issues"]}
    assert "blind_bid_sensitive_term" in codes
    assert "blind_bid_phone_number" in codes
    assert "blind_bid_specific_date" in codes
    assert all(issue["chapter_code"] == "2" for issue in report["issues"])
    assert all(issue["volume_type"] == "business" for issue in report["issues"])
    assert "重庆示例电力工程有限责任公司" not in str(report["issues"])
    assert all("matched_text_sha256" in issue for issue in report["issues"])


def test_blind_bid_report_uses_configured_terms_not_hardcoded_customer_names() -> None:
    report = build_blind_bid_report(
        "重庆示例电力工程有限责任公司具备施工能力。",
        sensitive_terms=[],
        chapter_code="8",
        volume_type="technical",
    )

    assert report["blind_check_passed"] is True
    assert report["issues"] == []


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
    assert estimate["estimated_pages_gate"] == estimate["estimated_pages"]
    assert estimate["method"]["gate_estimate_not_actual"] is True
    assert estimate["evidence"]["chart_count"] == 1
    assert estimate["evidence"]["table_row_count"] == 2
    assert estimate["evidence"]["explicit_page_break_count"] == 1


def test_estimate_markdown_pages_reports_actual_like_pages_near_measured_baseline():
    content = "施工组织" * 20187

    estimate = estimate_markdown_pages(content, target_pages=100)

    assert estimate["evidence"]["weighted_text_units"] >= 80745
    assert 70 <= estimate["estimated_pages_actual_like"] <= 90
    assert estimate["estimated_pages_gate"] > estimate["estimated_pages_actual_like"]


def test_page_gate_blocks_below_seventy_percent_target():
    gate = build_page_gate(target_pages=100, estimated_pages=65, actual_pages=None, actual_status="unchecked")

    assert gate["page_count_passed"] is False
    assert gate["page_count_status"] == "failed_estimate_below_minimum"
    assert gate["minimum_required_pages"] == 70


def test_page_gate_passes_with_warning_when_estimate_meets_minimum_but_unchecked():
    """When estimated_pages meets the 70% floor we pass with a warning so the
    chicken-and-egg between export and actual page counting can be broken."""
    gate = build_page_gate(target_pages=100, estimated_pages=80, actual_pages=None, actual_status="unchecked")

    assert gate["page_count_passed"] is True
    assert gate["page_count_status"] == "passed_by_estimate"
    assert "导出后" in gate["page_count_message"]


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


def test_chart_closure_report_warns_on_unallowed_chart_key_without_blocking():
    report = build_chart_closure_report(
        content_md="正文 {{chart:invented_architecture}}",
        chart_assets=[],
        allowed_chart_keys={"risk_matrix"},
    )

    assert report["chart_closure_passed"] is True
    assert report["issues"] == [
        {"code": "chart_key_not_allowed", "chart_key": "invented_architecture", "severity": "P1"}
    ]


def test_normalize_allowed_chart_keys_collects_strings_dicts_and_objects():
    class _Asset:
        placeholder_key = "schedule_main"
        chart_type = "schedule_gantt"

    assert normalize_allowed_chart_keys(
        ["risk_matrix"],
        [{"placeholder_key": "quality_main", "chart_type": "quality_system"}, _Asset(), "safety_system"],
    ) == {"quality_main", "quality_system", "risk_matrix", "safety_system", "schedule_gantt", "schedule_main"}


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


def test_coverage_report_uses_richest_duplicate_section_body_instead_of_empty_shell():
    content = "\n".join(
        [
            "## 8.1 编制依据",
            "",
            "## 8.1 编制依据与标准",
            "施工组织内容充分。" * 40,
        ]
    )
    checklist = [
        {"section_code": "8.1", "title": "编制依据", "min_chars": 50, "required_charts": [], "required_tables": []},
    ]

    report = build_coverage_report(content, checklist=checklist, constraints=[])

    assert report["coverage_passed"] is True
    assert report["issues"] == []


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


def test_chart_closure_report_accepts_mapping_like_chart_assets():
    asset = MappingProxyType({"placeholder_key": "risk_matrix", "status": "approved", "rendered_path": "/tmp/risk.png"})

    report = build_chart_closure_report(
        content_md="正文 {{chart:risk_matrix}}",
        chart_assets=[asset],
        inserted_chart_keys=["risk_matrix"],
    )

    assert report["chart_closure_passed"] is True
    assert report["asset_chart_count"] == 1
    assert report["approved_chart_count"] == 1
    assert report["rendered_chart_count"] == 1
    assert report["issues"] == []


def test_chart_closure_report_accepts_png_only_render_as_rendered():
    report = build_chart_closure_report(
        content_md="正文 {{chart:risk_matrix}}",
        chart_assets=[{"placeholder_key": "risk_matrix", "status": "approved", "rendered_png_path": "/tmp/risk.png"}],
        inserted_chart_keys=["risk_matrix"],
    )

    assert report["chart_closure_passed"] is True
    assert report["rendered_chart_count"] == 1
    assert report["issues"] == []


def test_coverage_report_does_not_treat_child_heading_as_required_parent_section():
    content = "## 8.1.1 子项\n子项内容充分。"
    checklist = [
        {"section_code": "8.1", "title": "编制依据", "min_chars": 1, "required_charts": [], "required_tables": []},
    ]

    report = build_coverage_report(content, checklist=checklist, constraints=[])

    assert report["coverage_passed"] is False
    assert any(issue["code"] == "missing_section" and issue["section_code"] == "8.1" for issue in report["issues"])


def test_coverage_report_flags_empty_equipment_and_personnel_tables() -> None:
    content = "## 8.13 资源配置\n{{equipment_table:vehicle}}\n{{equipment_table:machine}}\n{{personnel_table}}"
    checklist = [
        {
            "section_code": "8.13",
            "title": "资源配置",
            "min_chars": 0,
            "required_charts": [],
            "required_tables": ["equipment_table:vehicle", "equipment_table:machine", "personnel_table"],
        }
    ]

    report = build_coverage_report(
        content,
        checklist=checklist,
        constraints=[],
        equipment_data={"vehicle": [], "machine": []},
        personnel_data=[],
    )

    assert report["coverage_passed"] is False
    assert any(issue["code"] == "required_table_empty" and issue["table_key"] == "equipment_table:vehicle" for issue in report["issues"])
    assert any(issue["code"] == "required_table_empty" and issue["table_key"] == "equipment_table:machine" for issue in report["issues"])
    assert any(issue["code"] == "required_table_empty" and issue["table_key"] == "personnel_table" for issue in report["issues"])
