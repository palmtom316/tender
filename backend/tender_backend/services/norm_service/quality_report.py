from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, Iterable

from tender_backend.db.repositories.skill_definition_repo import SkillDefinitionRow
from tender_backend.services.norm_service.section_cleaning import (
    looks_like_backfilled_anchor,
    looks_like_front_matter_heading_noise,
    looks_like_suspicious_year_code,
    looks_like_terminal_heading_noise,
    looks_like_toc_noise,
    looks_like_unanchored_heading_noise,
)
from tender_backend.services.norm_service.validation import ValidationIssue, ValidationResult

if TYPE_CHECKING:
    from tender_backend.services.skill_catalog import SkillSpec


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 3)


def _gate(
    code: str,
    status: str,
    message: str,
    *,
    metric: float | int | None = None,
    threshold: float | int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "status": status,
        "message": message,
    }
    if metric is not None:
        payload["metric"] = metric
    if threshold is not None:
        payload["threshold"] = threshold
    return payload


def _serialize_issue(issue: ValidationIssue) -> dict[str, Any]:
    return {
        "code": getattr(issue, "code", None),
        "severity": getattr(issue, "severity", "warning"),
        "message": getattr(issue, "message", ""),
        "clause_no": getattr(issue, "clause_no", None),
        "page_start": getattr(issue, "page_start", None),
        "page_end": getattr(issue, "page_end", None),
    }


def _iter_anchor_pages(document_asset: Any) -> list[dict[str, Any]]:
    pages = []
    for page in getattr(document_asset, "pages", []):
        markdown = getattr(page, "normalized_text", None)
        if not isinstance(markdown, str) or not markdown.strip():
            continue
        page_number = getattr(page, "page_number", None)
        if not isinstance(page_number, int) or page_number <= 0:
            continue
        pages.append({"page_number": page_number, "markdown": markdown})
    return pages


def _severity_counts(validation: ValidationResult) -> dict[str, int]:
    counts = Counter((getattr(issue, "severity", None) or "warning") for issue in validation.issues)
    return dict(sorted(counts.items()))


def _issue_code_counts(validation: ValidationResult) -> dict[str, int]:
    counts = Counter(getattr(issue, "code", "unknown") for issue in validation.issues)
    return dict(sorted(counts.items()))


def _skill_catalog(
    available_skills: Iterable["SkillSpec"] | None,
    configured_skills: Iterable[SkillDefinitionRow] | None,
) -> tuple[dict[str, Any], dict[str, SkillDefinitionRow]]:
    if available_skills is None:
        from tender_backend.services.skill_catalog import default_skill_specs

        available_skills = default_skill_specs()
    catalog = {spec.skill_name: spec for spec in available_skills}
    configured = {row.skill_name: row for row in (configured_skills or [])}
    return catalog, configured


def _recommend_skills(
    *,
    overall_status: str,
    metrics: dict[str, Any],
    gates: list[dict[str, Any]],
    available_skills: Iterable["SkillSpec"] | None,
    configured_skills: Iterable[SkillDefinitionRow] | None,
) -> list[dict[str, Any]]:
    catalog, configured = _skill_catalog(available_skills, configured_skills)
    recommendations: list[dict[str, Any]] = []
    seen: set[str] = set()
    gate_status_by_code = {gate["code"]: gate["status"] for gate in gates}

    def add(skill_name: str, reason: str, trigger_codes: list[str]) -> None:
        if skill_name in seen:
            return
        spec = catalog.get(skill_name)
        row = configured.get(skill_name)
        if spec is None and row is None:
            return
        seen.add(skill_name)
        recommendations.append({
            "skill_name": skill_name,
            "description": (row.description if row else "") or (spec.description if spec else ""),
            "tool_names": list((row.tool_names if row else None) or (spec.tool_names if spec else [])),
            "active": row.active if row is not None else bool(spec and spec.active),
            "reason": reason,
            "trigger_codes": trigger_codes,
        })

    if gate_status_by_code.get("section_anchor_coverage") in {"warn", "fail"}:
        add(
            "mineru-standard-bundle",
            "OCR 段落锚点覆盖率偏低，适合先复盘页面 markdown、目录噪声和清洗前后差异。",
            ["section_anchor_coverage"],
        )
    if metrics.get("dropped_noise_count", 0) > 0 or metrics.get("backfilled_anchor_count", 0) > 0:
        add(
            "mineru-standard-bundle",
            "清洗阶段已经识别到噪声或回填锚点，适合继续核对 OCR 原始输出质量。",
            ["ocr_cleanup"],
        )
    if gate_status_by_code.get("structured_validation") in {"warn", "fail"}:
        add(
            "standard-parse-recovery",
            "结构化校验仍有问题，建议用恢复技能排查编号断裂、页码锚点和条款补丁。",
            ["structured_validation"],
        )
    if gate_status_by_code.get("table_capture") in {"warn", "fail"}:
        add(
            "standard-parse-recovery",
            "表格已被 OCR 识别，但结构化条款承接不足，建议重点检查表格转条款链路。",
            ["table_capture"],
        )
    if overall_status == "fail":
        add(
            "standard-parse-recovery",
            "整体质量门禁未通过，需要按标准解析恢复流程做定向回归。",
            ["overall"],
        )

    return recommendations


def build_standard_quality_report(
    *,
    document_asset: Any,
    raw_sections: list[dict[str, Any]],
    normalized_sections: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    clauses: list[dict[str, Any]],
    validation: ValidationResult,
    warnings: list[str] | None = None,
    available_skills: Iterable["SkillSpec"] | None = None,
    configured_skills: Iterable[SkillDefinitionRow] | None = None,
    executed_skills: list[dict[str, Any]] | None = None,
    ai_fallback_count: int = 0,
    total_parser_block_count: int = 0,
    max_ai_fallback_ratio: float = 0.15,
) -> dict[str, Any]:
    warning_messages = list(warnings or [])
    anchor_pages = _iter_anchor_pages(document_asset)
    phrase_flags = list(getattr(validation, "phrase_flags", []) or [])

    anchored_sections = sum(1 for section in normalized_sections if section.get("page_start") is not None)
    anchored_clauses = sum(1 for clause in clauses if clause.get("page_start") is not None)
    table_clause_count = sum(1 for clause in clauses if clause.get("source_type") == "table")
    commentary_clause_count = sum(1 for clause in clauses if clause.get("clause_type") == "commentary")

    noise_counts = {
        "toc_noise_count": sum(1 for section in raw_sections if looks_like_toc_noise(section)),
        "front_matter_noise_count": sum(1 for section in raw_sections if looks_like_front_matter_heading_noise(section)),
        "suspicious_year_code_count": sum(1 for section in raw_sections if looks_like_suspicious_year_code(section)),
        "unanchored_heading_noise_count": sum(1 for section in raw_sections if looks_like_unanchored_heading_noise(section)),
        "terminal_heading_noise_count": sum(1 for section in raw_sections if looks_like_terminal_heading_noise(section)),
    }
    dropped_noise_count = max(0, len(raw_sections) - len(normalized_sections))
    backfilled_anchor_count = sum(1 for section in normalized_sections if looks_like_backfilled_anchor(section))
    severity_counts = _severity_counts(validation)
    issue_code_counts = _issue_code_counts(validation)

    metrics: dict[str, Any] = {
        "page_count": len(anchor_pages),
        "raw_section_count": len(raw_sections),
        "normalized_section_count": len(normalized_sections),
        "table_count": len(tables),
        "clause_count": len(clauses),
        "commentary_clause_count": commentary_clause_count,
        "table_clause_count": table_clause_count,
        "anchored_section_count": anchored_sections,
        "anchored_clause_count": anchored_clauses,
        "section_anchor_coverage": _ratio(anchored_sections, len(normalized_sections)),
        "clause_anchor_coverage": _ratio(anchored_clauses, len(clauses)),
        "backfilled_anchor_count": backfilled_anchor_count,
        "dropped_noise_count": dropped_noise_count,
        "validation_issue_count": len(validation.issues),
        "validation_phrase_flag_count": len(phrase_flags),
        "validation_severity_counts": severity_counts,
        "validation_issue_code_counts": issue_code_counts,
        "ai_fallback_count": ai_fallback_count,
        "total_parser_block_count": total_parser_block_count,
        "ai_fallback_ratio": _ratio(ai_fallback_count, total_parser_block_count)
        if total_parser_block_count > 0
        else 0.0,
        **noise_counts,
    }

    section_anchor_coverage = metrics["section_anchor_coverage"]
    if not normalized_sections:
        section_gate = _gate("section_anchor_coverage", "fail", "规范 OCR 清洗后没有可用于结构化的段落。")
    elif section_anchor_coverage < 0.65:
        section_gate = _gate(
            "section_anchor_coverage",
            "fail",
            f"清洗后仅有 {anchored_sections}/{len(normalized_sections)} 个段落带页码锚点。",
            metric=section_anchor_coverage,
            threshold=0.85,
        )
    elif section_anchor_coverage < 0.85:
        section_gate = _gate(
            "section_anchor_coverage",
            "warn",
            f"清洗后段落锚点覆盖率为 {section_anchor_coverage:.1%}，建议抽查页码回填质量。",
            metric=section_anchor_coverage,
            threshold=0.85,
        )
    else:
        section_gate = _gate(
            "section_anchor_coverage",
            "pass",
            f"清洗后段落锚点覆盖率为 {section_anchor_coverage:.1%}。",
            metric=section_anchor_coverage,
            threshold=0.85,
        )

    clause_anchor_coverage = metrics["clause_anchor_coverage"]
    if clauses and clause_anchor_coverage < 0.75:
        clause_gate = _gate(
            "clause_anchor_coverage",
            "fail",
            f"结构化条款仅有 {anchored_clauses}/{len(clauses)} 个保留页码锚点。",
            metric=clause_anchor_coverage,
            threshold=0.9,
        )
    elif clauses and clause_anchor_coverage < 0.9:
        clause_gate = _gate(
            "clause_anchor_coverage",
            "warn",
            f"结构化条款页码锚点覆盖率为 {clause_anchor_coverage:.1%}。",
            metric=clause_anchor_coverage,
            threshold=0.9,
        )
    else:
        clause_gate = _gate(
            "clause_anchor_coverage",
            "pass",
            "结构化条款页码锚点覆盖正常。",
            metric=clause_anchor_coverage,
            threshold=0.9,
        )

    validation_issue_count = len(validation.issues)
    validation_error_count = severity_counts.get("error", 0)
    if validation_error_count > 0 or validation_issue_count >= 8:
        validation_gate = _gate(
            "structured_validation",
            "fail",
            f"结构化校验发现 {validation_issue_count} 个问题，需要回归排查。",
            metric=validation_issue_count,
            threshold=0,
        )
    elif validation_issue_count > 0:
        validation_gate = _gate(
            "structured_validation",
            "warn",
            f"结构化校验发现 {validation_issue_count} 个问题，建议抽样复核。",
            metric=validation_issue_count,
            threshold=0,
        )
    else:
        validation_gate = _gate(
            "structured_validation",
            "pass",
            "结构化校验未发现问题。",
            metric=validation_issue_count,
            threshold=0,
        )

    if metrics["table_count"] <= 0:
        table_gate = _gate("table_capture", "pass", "OCR 未识别到表格，无需表格条款承接。")
    elif table_clause_count <= 0 and metrics["table_count"] >= 3:
        table_gate = _gate(
            "table_capture",
            "fail",
            f"OCR 识别出 {metrics['table_count']} 个表格，但结构化结果没有表格来源条款。",
            metric=table_clause_count,
            threshold=1,
        )
    elif table_clause_count <= 0:
        table_gate = _gate(
            "table_capture",
            "warn",
            f"OCR 识别出 {metrics['table_count']} 个表格，但结构化结果没有表格来源条款。",
            metric=table_clause_count,
            threshold=1,
        )
    else:
        table_gate = _gate(
            "table_capture",
            "pass",
            f"已产出 {table_clause_count} 个表格来源条款。",
            metric=table_clause_count,
            threshold=1,
        )

    if dropped_noise_count > 0 or backfilled_anchor_count > 0:
        cleanup_gate = _gate(
            "ocr_cleanup",
            "warn",
            f"清洗阶段过滤 {dropped_noise_count} 个疑似噪声段落，并回填 {backfilled_anchor_count} 个页码锚点。",
            metric=dropped_noise_count + backfilled_anchor_count,
            threshold=0,
        )
    else:
        cleanup_gate = _gate("ocr_cleanup", "pass", "OCR 清洗阶段未发现明显噪声或锚点缺口。")

    ai_fallback_ratio = metrics["ai_fallback_ratio"]
    if total_parser_block_count <= 0:
        ai_gate = _gate("ai_fallback_ratio", "pass", "没有需要 AI fallback 的确定性解析块。")
    elif ai_fallback_ratio > max_ai_fallback_ratio:
        ai_gate = _gate(
            "ai_fallback_ratio",
            "fail",
            f"AI fallback 比例为 {ai_fallback_ratio:.1%}，超过确定性解析覆盖门禁。",
            metric=ai_fallback_ratio,
            threshold=max_ai_fallback_ratio,
        )
    elif ai_fallback_count > 0:
        ai_gate = _gate(
            "ai_fallback_ratio",
            "warn",
            f"AI fallback 比例为 {ai_fallback_ratio:.1%}，建议抽查模型输出 artifact。",
            metric=ai_fallback_ratio,
            threshold=max_ai_fallback_ratio,
        )
    else:
        ai_gate = _gate(
            "ai_fallback_ratio",
            "pass",
            "确定性解析覆盖全部块，未使用 AI fallback。",
            metric=ai_fallback_ratio,
            threshold=max_ai_fallback_ratio,
        )

    gates = [
        section_gate,
        clause_gate,
        validation_gate,
        table_gate,
        cleanup_gate,
        ai_gate,
    ]

    gate_statuses = {gate["status"] for gate in gates}
    if "fail" in gate_statuses:
        overall_status = "fail"
        summary = "当前解析质量未通过门禁，建议先做定向回归再入库。"
    elif "warn" in gate_statuses:
        overall_status = "review"
        summary = "当前解析质量可继续抽查，但仍有风险信号需要复核。"
    else:
        overall_status = "pass"
        summary = "当前解析质量通过门禁，可进入常规抽样验收。"

    recommended_skills = _recommend_skills(
        overall_status=overall_status,
        metrics=metrics,
        gates=gates,
        available_skills=available_skills,
        configured_skills=configured_skills,
    )
    skill_catalog, configured_skill_map = _skill_catalog(available_skills, configured_skills)
    available_skill_payloads: list[dict[str, Any]] = []
    disabled_parse_plugins: list[dict[str, Any]] = []
    for spec in sorted(skill_catalog.values(), key=lambda item: item.skill_name):
        row = configured_skill_map.get(spec.skill_name)
        active = row.active if row is not None else bool(spec.active)
        payload = {
            "skill_name": spec.skill_name,
            "description": (row.description if row else "") or spec.description,
            "tool_names": list((row.tool_names if row else None) or spec.tool_names),
            "active": active,
            "skill_type": getattr(spec, "skill_type", "documentation"),
            "hook_names": list(getattr(spec, "hook_names", None) or []),
        }
        available_skill_payloads.append(payload)
        if payload["skill_type"] == "parse_plugin" and not active:
            disabled_parse_plugins.append(payload)

    return {
        "overview": {
            "status": overall_status,
            "summary": summary,
        },
        "metrics": metrics,
        "gates": gates,
        "warnings": warning_messages[:10],
        "top_issues": [_serialize_issue(issue) for issue in validation.issues[:5]],
        "recommended_skills": recommended_skills,
        "executed_skills": list(executed_skills or []),
        "available_skills": available_skill_payloads,
        "disabled_parse_plugins": disabled_parse_plugins,
    }
