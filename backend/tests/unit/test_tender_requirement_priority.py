from __future__ import annotations

from uuid import uuid4

from tender_backend.services.tender_requirement_priority import apply_tender_requirement_context


def test_apply_tender_requirement_context_adds_override_policy() -> None:
    requirement_id = str(uuid4())
    overrides = {
        "priority_policy": "tender_extracted_requirements_override_template",
        "content_requirements": [{"id": requirement_id, "category": "technical", "requirement_text": "按招标文件技术要求响应"}],
        "format_requirements": [{"category": "format", "requirement_text": "正文小四号"}],
        "all_requirements": [],
        "summary": {
            "content_requirement_count": 1,
            "format_requirement_count": 1,
            "total_requirement_count": 2,
        },
    }

    context = apply_tender_requirement_context({"company": {"company_name": "测试公司"}}, overrides)

    assert context["company"]["company_name"] == "测试公司"
    assert context["tender_requirement_priority"]["policy"] == "tender_extracted_requirements_override_template"
    assert context["tender_content_requirements"][0]["id"] == requirement_id
    assert context["tender_format_requirements"][0]["requirement_text"] == "正文小四号"
