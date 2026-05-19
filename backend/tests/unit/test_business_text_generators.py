from __future__ import annotations

from typing import Any

from tender_backend.services.business_text_generators import (
    BUSINESS_TEXT_GENERATOR_SPECS,
    generate_business_text,
)
from tender_backend.services.template_service.business_chapter_bindings import (
    BUSINESS_TEXT_GENERATOR_BINDINGS,
)


def test_business_text_generators_cover_required_sections() -> None:
    required = {"11", "13.1", "15", "17", "24.5"}

    assert set(BUSINESS_TEXT_GENERATOR_SPECS) == required
    assert set(BUSINESS_TEXT_GENERATOR_BINDINGS) == required


def test_generate_business_text_uses_fake_gateway_without_blind_sensitive_fields() -> None:
    calls: list[dict[str, Any]] = []

    def fake_gateway(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return {"content": "## 绿色发展\n\n已建立绿色施工管理机制。"}

    result = generate_business_text(
        "11",
        {
            "company": {
                "company_name": "重庆示例电力工程有限责任公司",
                "legal_representative": "张三",
                "contact_phone": "13800000000",
            },
            "tender": {"project_name": "配网工程", "purchaser_name": "REDACTED"},
            "green_plans": [
                {
                    "title": "绿色施工制度",
                    "summary": "使用可回收材料并控制扬尘。",
                    "evidence_asset_id": "asset-green-1",
                }
            ],
            "scoring_points": ["绿色施工措施完整"],
            "template_requirements": ["说明绿色发展顶层规划及执行情况"],
        },
        completion_fn=fake_gateway,
    )

    assert result["content_md"].startswith("## 绿色发展")
    assert result["missing_materials"] == []
    assert result["evidence_refs"] == ["asset-green-1"]
    prompt_blob = str(calls[0]["messages"])
    assert "重庆示例电力工程有限责任公司" not in prompt_blob
    assert "张三" not in prompt_blob
    assert "13800000000" not in prompt_blob
    assert "配网工程" not in prompt_blob
    assert "绿色施工制度" in prompt_blob


def test_generate_business_text_reports_missing_materials_without_calling_gateway() -> None:
    called = False

    def fake_gateway(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"content": "不应调用"}

    result = generate_business_text(
        "15",
        {
            "company": {"company_name": "重庆示例电力工程有限责任公司"},
            "tender": {"project_name": "配网工程"},
        },
        completion_fn=fake_gateway,
    )

    assert called is False
    assert result["content_md"] == ""
    assert result["missing_materials"] == [
        {"chapter_code": "15", "material_key": "technology_achievements", "reason": "missing_required_material"}
    ]
