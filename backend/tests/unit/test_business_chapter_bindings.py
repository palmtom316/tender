from __future__ import annotations

import pytest

from tender_backend.services.bid_outline_templates import SGCC_DISTRIBUTION_BUSINESS_CHAPTERS
from tender_backend.services.template_service.business_chapter_bindings import (
    BUSINESS_CHAPTER_BINDINGS,
    ChapterBinding,
    build_company_name_change_context,
    build_business_chapter_context,
    build_no_violation_commitment_context,
    build_sgcc_personnel_relation_context,
    build_small_taxpayer_context,
    get_business_chapter_binding,
)


def _full_materials() -> dict:
    asset_categories = {
        category
        for binding in BUSINESS_CHAPTER_BINDINGS.values()
        for category in binding.asset_categories
    }
    return {
        "company": {"company_name": "重庆示例电力工程有限责任公司", "legal_representative": "张三"},
        "tender": {"project_name": "配网工程", "purchaser_name": "REDACTED"},
        "assets": [
            {"asset_category": category, "file_name": f"{category}.pdf"}
            for category in sorted(asset_categories)
        ],
        "people": [{"full_name": "唐玮", "role_name": "项目经理"}],
        "certificates": [{"certificate_name": "质量管理体系认证证书"}],
        "performances": [{"project_name": "10kV配网改造"}],
        "financial_statements": [{"fiscal_year": 2024, "statement_type": "annual_report"}],
        "financial_assets": [{"file_name": "2024审计报告.pdf"}],
        "bank_accounts": [{"account_name": "基本户"}],
        "green_plans": [{"title": "绿色发展规划"}],
        "esg_reports": [{"report_year": 2024}],
        "green_certificates": [{"certificate_no": "GEC-001"}],
        "technology_achievements": [{"title": "科技成果"}],
        "innovation_policies": [{"title": "创新激励制度"}],
        "awards": [{"award_name": "质量奖"}],
        "bid_bonds": [{"amount": "10000"}],
        "commit_date": "2026-05-19",
        "signature_block": {"signer": "法定代表人"},
    }


def test_business_chapter_bindings_cover_24_top_level_chapters() -> None:
    expected_codes = {str(idx) for idx in range(1, 25)}
    top_level_codes = {
        chapter["chapter_code"]
        for chapter in SGCC_DISTRIBUTION_BUSINESS_CHAPTERS
        if "." not in chapter["chapter_code"]
    }

    assert top_level_codes == expected_codes
    assert set(BUSINESS_CHAPTER_BINDINGS) == expected_codes
    assert all(isinstance(binding, ChapterBinding) for binding in BUSINESS_CHAPTER_BINDINGS.values())


@pytest.mark.parametrize("chapter_code", [str(idx) for idx in range(1, 25)])
def test_each_business_chapter_builder_returns_context_shape_for_full_materials(chapter_code: str) -> None:
    binding = get_business_chapter_binding(chapter_code)
    result = binding.context_builder(chapter_code, _full_materials(), binding)

    assert result["chapter_code"] == chapter_code
    assert result["company"]["company_name"] == "重庆示例电力工程有限责任公司"
    assert result["tender"]["project_name"] == "配网工程"
    assert result["missing_materials"] == []


def test_build_business_chapter_context_wraps_render_context_for_assembler_consumers() -> None:
    result = build_business_chapter_context("5", _full_materials())

    assert result["chapter_code"] == "5"
    assert result["context"]["company"]["company_name"] == "重庆示例电力工程有限责任公司"
    assert result["context"]["tender"]["project_name"] == "配网工程"
    assert isinstance(result["asset_categories"], list)
    assert result["missing_materials"] == []


@pytest.mark.parametrize("chapter_code", ["1", "3", "4", "9", "22"])
def test_generic_attachment_builders_report_missing_assets_as_structured_gaps(chapter_code: str) -> None:
    result = build_business_chapter_context(
        chapter_code,
        {
            "company": {"company_name": "重庆示例电力工程有限责任公司"},
            "tender": {"project_name": "配网工程"},
        },
    )

    assert result["context"]["company"]["company_name"] == "重庆示例电力工程有限责任公司"
    assert result["context"]["tender"]["project_name"] == "配网工程"
    assert {"chapter_code": chapter_code, "material_key": "asset", "reason": "missing_required_material"} in result["missing_materials"]


@pytest.mark.parametrize("chapter_code", ["2", "7", "20", "21"])
def test_commitment_builders_return_company_tender_and_signature_block(chapter_code: str) -> None:
    result = build_business_chapter_context(
        chapter_code,
        {
            "company": {"company_name": "重庆示例电力工程有限责任公司", "legal_representative": "张三"},
            "tender": {"project_name": "配网工程", "purchaser_name": "REDACTED"},
            "commit_date": "2026-05-19",
            "signature_block": {"signer": "法定代表人"},
        },
    )

    assert result["context"]["company"]["company_name"] == "重庆示例电力工程有限责任公司"
    assert result["context"]["company"]["legal_representative"] == "张三"
    assert result["context"]["tender"]["project_name"] == "配网工程"
    assert result["context"]["tender"]["purchaser_name"] == "REDACTED"
    assert result["context"]["commit_date"] == "2026-05-19"
    assert result["context"]["signature_block"]["signer"] == "法定代表人"
    assert result["missing_materials"] == []


@pytest.mark.parametrize(
    ("chapter_code", "builder"),
    [
        ("2", build_no_violation_commitment_context),
        ("7", build_sgcc_personnel_relation_context),
        ("20", build_company_name_change_context),
        ("21", build_small_taxpayer_context),
    ],
)
def test_named_commitment_builders_require_fixed_fields(chapter_code: str, builder) -> None:
    binding = get_business_chapter_binding(chapter_code)

    result = builder(chapter_code, {}, binding)

    assert result["chapter_code"] == chapter_code
    assert result["missing_materials"] == [
        {"chapter_code": chapter_code, "material_key": "company.company_name", "reason": "missing_required_material"},
        {"chapter_code": chapter_code, "material_key": "company.legal_representative", "reason": "missing_required_material"},
        {"chapter_code": chapter_code, "material_key": "tender.purchaser_name", "reason": "missing_required_material"},
        {"chapter_code": chapter_code, "material_key": "tender.project_name", "reason": "missing_required_material"},
        {"chapter_code": chapter_code, "material_key": "commit_date", "reason": "missing_required_material"},
        {"chapter_code": chapter_code, "material_key": "signature_block", "reason": "missing_required_material"},
    ]


@pytest.mark.parametrize(
    ("chapter_code", "ledger_key"),
    [
        ("10", "bank_accounts"),
        ("11", "green_plans"),
        ("13", "esg_reports"),
        ("14", "green_certificates"),
        ("15", "technology_achievements"),
        ("16", "innovation_policies"),
        ("18", "awards"),
        ("23", "bid_bonds"),
    ],
)
def test_specialty_ledger_builders_report_structured_gaps_without_fabricating_data(
    chapter_code: str,
    ledger_key: str,
) -> None:
    result = build_business_chapter_context(
        chapter_code,
        {
            "company": {"company_name": "重庆示例电力工程有限责任公司"},
            "tender": {"project_name": "配网工程"},
        },
    )

    assert ledger_key not in result["context"]
    assert {"chapter_code": chapter_code, "material_key": ledger_key, "reason": "missing_specialty_ledger"} in result["missing_materials"]


def test_company_profile_binding_returns_template_context_keys() -> None:
    result = build_business_chapter_context(
        "5",
        {
            "company": {"company_name": "重庆示例电力工程有限责任公司"},
            "tender": {"project_name": "配网工程"},
            "assets": [{"asset_category": "business_license", "file_name": "营业执照.pdf"}],
        },
    )

    assert result["context"]["company"]["company_name"] == "重庆示例电力工程有限责任公司"
    assert result["context"]["tender"]["project_name"] == "配网工程"
    assert result["context"]["asset"][0]["file_name"] == "营业执照.pdf"
    assert result["missing_materials"] == []


def test_attachment_index_alias_feeds_asset_context() -> None:
    result = build_business_chapter_context(
        "3",
        {
            "company": {"company_name": "重庆示例电力工程有限责任公司"},
            "tender": {"project_name": "配网工程"},
            "attachment_index": [{"asset_category": "business_license", "file_name": "营业执照.pdf"}],
        },
    )

    assert result["context"]["asset"][0]["file_name"] == "营业执照.pdf"
    assert result["missing_materials"] == []


def test_people_binding_uses_personnel_and_reports_missing_company() -> None:
    result = build_business_chapter_context(
        "6",
        {
            "tender": {"project_name": "配网工程"},
            "people": [{"full_name": "唐玮", "role_name": "项目经理"}],
        },
    )

    assert result["context"]["people"][0]["full_name"] == "唐玮"
    assert result["context"]["tender"]["project_name"] == "配网工程"
    assert result["missing_materials"] == [
        {"chapter_code": "6", "material_key": "company", "reason": "missing_required_material"}
    ]


def test_certificate_performance_and_financial_builders_reuse_existing_master_data() -> None:
    materials = {
        "company": {"company_name": "重庆示例电力工程有限责任公司"},
        "tender": {"project_name": "配网工程"},
        "certificates": [{"certificate_name": "质量管理体系认证证书"}],
        "performances": [{"project_name": "10kV配网改造"}],
        "financial_statements": [{"fiscal_year": 2024, "statement_type": "annual_report"}],
        "financial_assets": [{"file_name": "2024审计报告.pdf"}],
    }

    cert_result = build_business_chapter_context("12", materials)
    perf_result = build_business_chapter_context("24", materials)
    finance_result = build_business_chapter_context("8", materials)

    assert cert_result["context"]["certificates"][0]["certificate_name"] == "质量管理体系认证证书"
    assert perf_result["context"]["performances"][0]["project_name"] == "10kV配网改造"
    assert finance_result["context"]["financial_statements"][0]["fiscal_year"] == 2024
    assert finance_result["context"]["asset"][0]["file_name"] == "2024审计报告.pdf"


def test_financial_attachments_alias_feeds_financial_asset_context() -> None:
    result = build_business_chapter_context(
        "8",
        {
            "company": {"company_name": "重庆示例电力工程有限责任公司"},
            "tender": {"project_name": "配网工程"},
            "financial_statements": [{"fiscal_year": 2024, "statement_type": "annual_report"}],
            "financial_attachments": [{"file_name": "2024审计报告.pdf"}],
        },
    )

    assert result["context"]["asset"][0]["file_name"] == "2024审计报告.pdf"
    assert result["missing_materials"] == []


def test_missing_specialty_ledger_is_structured_gap_not_fabricated_data() -> None:
    result = build_business_chapter_context(
        "10",
        {
            "company": {"company_name": "重庆示例电力工程有限责任公司"},
            "tender": {"project_name": "配网工程"},
        },
    )

    assert result["context"]["company"]["company_name"] == "重庆示例电力工程有限责任公司"
    assert "bank_accounts" not in result["context"]
    assert result["missing_materials"] == [
        {"chapter_code": "10", "material_key": "bank_accounts", "reason": "missing_specialty_ledger"}
    ]


def test_get_business_chapter_binding_rejects_unknown_chapter() -> None:
    try:
        get_business_chapter_binding("25")
    except KeyError as exc:
        assert "business chapter binding not found" in str(exc)
    else:
        raise AssertionError("expected KeyError")
