"""Business bid narrative generators.

The generator builds a constrained AI payload from companybase facts and tender
requirements, while stripping blind-bid-sensitive identity fields before the
payload leaves the process.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


CompletionFn = Callable[[dict[str, Any]], Mapping[str, Any] | str]

_SENSITIVE_KEYS = {
    "company_name",
    "legal_representative",
    "contact_name",
    "contact_phone",
    "email",
    "full_name",
    "phone",
    "project_name",
    "purchaser_name",
    "registered_address",
    "signer",
    "unified_social_credit_code",
}


@dataclass(frozen=True)
class BusinessTextGeneratorSpec:
    chapter_code: str
    generator_name: str
    title: str
    required_material_keys: tuple[str, ...]


BUSINESS_TEXT_GENERATOR_SPECS: dict[str, BusinessTextGeneratorSpec] = {
    "11": BusinessTextGeneratorSpec(
        chapter_code="11",
        generator_name="green_development",
        title="绿色发展顶层规划及执行情况",
        required_material_keys=("green_plans",),
    ),
    "13.1": BusinessTextGeneratorSpec(
        chapter_code="13.1",
        generator_name="esg_report",
        title="ESG报告",
        required_material_keys=("esg_reports",),
    ),
    "15": BusinessTextGeneratorSpec(
        chapter_code="15",
        generator_name="technology_achievement",
        title="取得的科技成果",
        required_material_keys=("technology_achievements",),
    ),
    "17": BusinessTextGeneratorSpec(
        chapter_code="17",
        generator_name="research_team",
        title="研发团队规模",
        required_material_keys=("people",),
    ),
    "24.5": BusinessTextGeneratorSpec(
        chapter_code="24.5",
        generator_name="business_strength",
        title="综合实力",
        required_material_keys=("performances",),
    ),
}


def generate_business_text(
    chapter_code: str,
    context: Mapping[str, Any],
    *,
    completion_fn: CompletionFn,
) -> dict[str, Any]:
    spec = BUSINESS_TEXT_GENERATOR_SPECS[chapter_code]
    missing_materials = _missing_required_materials(spec, context)
    evidence_refs = _evidence_refs(context)
    if missing_materials:
        return {"content_md": "", "evidence_refs": evidence_refs, "missing_materials": missing_materials}

    payload = {
        "task_type": "generate_business_bid_text",
        "messages": _messages(spec, context),
        "metadata": {
            "chapter_code": spec.chapter_code,
            "generator_name": spec.generator_name,
            "evidence_refs": evidence_refs,
        },
    }
    response = completion_fn(payload)
    content = _response_content(response)
    return {
        "content_md": content,
        "evidence_refs": evidence_refs,
        "missing_materials": [],
    }


def _missing_required_materials(
    spec: BusinessTextGeneratorSpec,
    context: Mapping[str, Any],
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for key in spec.required_material_keys:
        value = context.get(key)
        if value:
            continue
        missing.append(
            {
                "chapter_code": spec.chapter_code,
                "material_key": key,
                "reason": "missing_required_material",
            }
        )
    return missing


def _messages(spec: BusinessTextGeneratorSpec, context: Mapping[str, Any]) -> list[dict[str, str]]:
    safe_context = _sanitize_for_prompt(context)
    user_payload = {
        "chapter_code": spec.chapter_code,
        "chapter_title": spec.title,
        "generator_name": spec.generator_name,
        "facts": safe_context,
        "requirements": {
            "scoring_points": safe_context.get("scoring_points") or [],
            "template_requirements": safe_context.get("template_requirements") or [],
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "你是投标商务标正文生成器。只使用输入事实和证据引用写正文；"
                "缺失事实不得编造；不得输出公司、人员、项目等暗标敏感身份信息。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def _sanitize_for_prompt(value: Any, *, key: str | None = None) -> Any:
    if key in _SENSITIVE_KEYS:
        return None
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for child_key, child_value in value.items():
            safe_value = _sanitize_for_prompt(child_value, key=str(child_key))
            if safe_value is not None:
                sanitized[str(child_key)] = safe_value
        return sanitized
    if isinstance(value, list):
        return [
            safe_item
            for item in value
            if (safe_item := _sanitize_for_prompt(item, key=key)) is not None
        ]
    return value


def _evidence_refs(value: Any) -> list[str]:
    refs: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key in ("evidence_ref", "evidence_asset_id", "file_name"):
                ref = node.get(key)
                if ref:
                    refs.append(str(ref))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return list(dict.fromkeys(refs))


def _response_content(response: Mapping[str, Any] | str) -> str:
    if isinstance(response, str):
        return response.strip()
    for key in ("content_md", "content", "text"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


__all__ = [
    "BUSINESS_TEXT_GENERATOR_SPECS",
    "BusinessTextGeneratorSpec",
    "generate_business_text",
]
