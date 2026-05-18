from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


ContextBuilder = Callable[[str, Mapping[str, Any], "ChapterBinding"], dict[str, Any]]


@dataclass(frozen=True)
class ChapterBinding:
    chapter_code: str
    context_builder: ContextBuilder
    asset_categories: tuple[str, ...] = ()
    narrative_generator: str | None = None


def _records(materials: Mapping[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = materials.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    return []


def _record(materials: Mapping[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = materials.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return None


def _missing(chapter_code: str, material_key: str, *, reason: str = "missing_required_material") -> dict[str, str]:
    return {"chapter_code": chapter_code, "material_key": material_key, "reason": reason}


def _assets_for_categories(materials: Mapping[str, Any], categories: tuple[str, ...]) -> list[dict[str, Any]]:
    assets = _records(materials, "assets", "evidence_assets", "asset_index", "attachment_index")
    if not categories:
        return assets
    return [
        asset for asset in assets
        if str(asset.get("asset_category") or asset.get("asset_type") or "") in categories
    ]


def _base_context(
    chapter_code: str,
    materials: Mapping[str, Any],
    binding: ChapterBinding,
    *,
    require_company: bool = True,
    require_tender: bool = True,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    context: dict[str, Any] = {}
    missing_materials: list[dict[str, str]] = []

    company = _record(materials, "company", "company_profile", "company_subject")
    tender = _record(materials, "tender", "project", "tender_project")
    assets = _assets_for_categories(materials, binding.asset_categories)

    if company:
        context["company"] = company
    elif require_company:
        missing_materials.append(_missing(chapter_code, "company"))

    if tender:
        context["tender"] = tender
    elif require_tender:
        missing_materials.append(_missing(chapter_code, "tender"))

    if assets:
        context["asset"] = assets

    return context, missing_materials


def _generic_attachment_context(chapter_code: str, materials: Mapping[str, Any], binding: ChapterBinding) -> dict[str, Any]:
    context, missing_materials = _base_context(chapter_code, materials, binding)
    if binding.asset_categories and "asset" not in context:
        missing_materials.append(_missing(chapter_code, "asset"))
    return {**context, "chapter_code": chapter_code, "missing_materials": missing_materials}


def _company_profile_context(chapter_code: str, materials: Mapping[str, Any], binding: ChapterBinding) -> dict[str, Any]:
    context, missing_materials = _base_context(chapter_code, materials, binding)
    return {**context, "chapter_code": chapter_code, "missing_materials": missing_materials}


def _people_context(chapter_code: str, materials: Mapping[str, Any], binding: ChapterBinding) -> dict[str, Any]:
    context, missing_materials = _base_context(chapter_code, materials, binding)
    people = _records(materials, "people", "personnel", "person_profiles")
    if people:
        context["people"] = people
    else:
        missing_materials.append(_missing(chapter_code, "people"))
    return {**context, "chapter_code": chapter_code, "missing_materials": missing_materials}


def _certificate_context(chapter_code: str, materials: Mapping[str, Any], binding: ChapterBinding) -> dict[str, Any]:
    context, missing_materials = _base_context(chapter_code, materials, binding)
    certificates = _records(materials, "certificates", "qualification_certificates")
    if certificates:
        context["certificates"] = certificates
    elif "asset" not in context:
        missing_materials.append(_missing(chapter_code, "certificates"))
    return {**context, "chapter_code": chapter_code, "missing_materials": missing_materials}


def _performance_context(chapter_code: str, materials: Mapping[str, Any], binding: ChapterBinding) -> dict[str, Any]:
    context, missing_materials = _base_context(chapter_code, materials, binding, require_tender=False)
    performances = _records(materials, "performances", "project_performances")
    if performances:
        context["performances"] = performances
    else:
        missing_materials.append(_missing(chapter_code, "performances"))
    return {**context, "chapter_code": chapter_code, "missing_materials": missing_materials}


def _financial_context(chapter_code: str, materials: Mapping[str, Any], binding: ChapterBinding) -> dict[str, Any]:
    context, missing_materials = _base_context(chapter_code, materials, binding)
    statements = _records(materials, "financial_statements")
    financial_assets = _records(materials, "financial_assets", "financial_attachments")
    if statements:
        context["financial_statements"] = statements
    else:
        missing_materials.append(_missing(chapter_code, "financial_statements"))
    if financial_assets:
        context["asset"] = financial_assets
    elif "asset" not in context:
        missing_materials.append(_missing(chapter_code, "financial_assets"))
    return {**context, "chapter_code": chapter_code, "missing_materials": missing_materials}


def _specialty_ledger_context(
    ledger_key: str,
    chapter_code: str,
    materials: Mapping[str, Any],
    binding: ChapterBinding,
) -> dict[str, Any]:
    context, missing_materials = _base_context(chapter_code, materials, binding)
    rows = _records(materials, ledger_key)
    if rows:
        context[ledger_key] = rows
    else:
        missing_materials.append(_missing(chapter_code, ledger_key, reason="missing_specialty_ledger"))
    return {**context, "chapter_code": chapter_code, "missing_materials": missing_materials}


def _commitment_context(chapter_code: str, materials: Mapping[str, Any], binding: ChapterBinding) -> dict[str, Any]:
    context, missing_materials = _base_context(chapter_code, materials, binding)
    signature = _record(materials, "signature_block")
    if signature:
        context["signature_block"] = signature
    return {**context, "chapter_code": chapter_code, "missing_materials": missing_materials}


def _ledger_builder(ledger_key: str) -> ContextBuilder:
    return lambda chapter_code, materials, binding: _specialty_ledger_context(ledger_key, chapter_code, materials, binding)


BUSINESS_CHAPTER_BINDINGS: dict[str, ChapterBinding] = {
    "1": ChapterBinding("1", _generic_attachment_context, ("business_deviation",)),
    "2": ChapterBinding("2", _commitment_context, ("commitment",)),
    "3": ChapterBinding("3", _generic_attachment_context, ("business_license",)),
    "4": ChapterBinding("4", _generic_attachment_context, ("legal_representative_id",)),
    "5": ChapterBinding("5", _company_profile_context, ("company_profile", "business_license")),
    "6": ChapterBinding("6", _people_context, ("credit_report", "personnel_certificate")),
    "7": ChapterBinding("7", _commitment_context, ("relationship_statement",)),
    "8": ChapterBinding("8", _financial_context, ("financial_report", "audit_report")),
    "9": ChapterBinding("9", _generic_attachment_context, ("consortium_agreement",)),
    "10": ChapterBinding("10", _ledger_builder("bank_accounts"), ("bank_account",)),
    "11": ChapterBinding("11", _ledger_builder("green_plans"), ("green_plan",), narrative_generator="green_development"),
    "12": ChapterBinding("12", _certificate_context, ("green_management_certificate", "quality_certificate", "safety_certificate")),
    "13": ChapterBinding("13", _ledger_builder("esg_reports"), ("esg_report", "environmental_report")),
    "14": ChapterBinding("14", _ledger_builder("green_certificates"), ("green_certificate",)),
    "15": ChapterBinding("15", _ledger_builder("technology_achievements"), ("technology_achievement",), narrative_generator="technology_achievement"),
    "16": ChapterBinding("16", _ledger_builder("innovation_policies"), ("innovation_policy",), narrative_generator="innovation_policy"),
    "17": ChapterBinding("17", _people_context, ("research_team",)),
    "18": ChapterBinding("18", _ledger_builder("awards"), ("quality_award", "industry_award")),
    "19": ChapterBinding("19", _certificate_context, ("high_tech_certificate",)),
    "20": ChapterBinding("20", _commitment_context, ("name_change_certificate",)),
    "21": ChapterBinding("21", _commitment_context, ("taxpayer_certificate",)),
    "22": ChapterBinding("22", _generic_attachment_context, ("tax_rate_evidence",)),
    "23": ChapterBinding("23", _ledger_builder("bid_bonds"), ("bid_bond", "deposit_voucher")),
    "24": ChapterBinding("24", _performance_context, ("credit_report", "other_business"), narrative_generator="business_strength"),
}


def get_business_chapter_binding(chapter_code: str) -> ChapterBinding:
    try:
        return BUSINESS_CHAPTER_BINDINGS[chapter_code]
    except KeyError as exc:
        raise KeyError(f"business chapter binding not found: {chapter_code}") from exc


def build_business_chapter_context(chapter_code: str, materials: Mapping[str, Any]) -> dict[str, Any]:
    binding = get_business_chapter_binding(chapter_code)
    raw_context = dict(binding.context_builder(chapter_code, materials, binding))
    raw_context.setdefault("chapter_code", chapter_code)
    missing_materials = list(raw_context.pop("missing_materials", []))
    raw_context.pop("chapter_code", None)
    result = {
        "chapter_code": chapter_code,
        "context": raw_context,
        "missing_materials": missing_materials,
        "asset_categories": list(binding.asset_categories),
    }
    if binding.narrative_generator:
        result["narrative_generator"] = binding.narrative_generator
    return result


__all__ = [
    "BUSINESS_CHAPTER_BINDINGS",
    "ChapterBinding",
    "build_business_chapter_context",
    "get_business_chapter_binding",
]
