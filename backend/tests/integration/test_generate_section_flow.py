"""Integration test for generate_section workflow and eval runner."""

from __future__ import annotations

import pytest

import tender_backend.workflows.generate_section  # noqa: F401
from tender_backend.workflows.registry import get_workflow, list_workflows
from tender_backend.services.prompt_service import PromptService
from tender_backend.tools.registry import list_tools
import tender_backend.tools.search_clauses  # noqa: F401
import tender_backend.tools.search_sections  # noqa: F401
import tender_backend.tools.assemble_evidence_pack  # noqa: F401
from tests.evals.eval_runner import eval_fact_consistency, eval_compliance_coverage


def test_generate_section_workflow_registered():
    assert "generate_section" in list_workflows()


def test_generate_section_has_expected_steps():
    wf_cls = get_workflow("generate_section")
    wf = wf_cls()
    step_names = [s.name for s in wf.steps]
    assert step_names == [
        "load_project_facts",
        "load_section_requirements",
        "search_clauses",
        "search_sections",
        "assemble_evidence_pack",
        "llm_generate_outline",
        "human_confirm_outline",
        "llm_generate_section",
        "save_draft",
    ]


def test_tools_registered():
    tools = list_tools()
    assert "search_clauses" in tools
    assert "search_sections" in tools
    assert "assemble_evidence_pack" in tools


def test_prompt_service_render():
    svc = PromptService()
    template = "生成{{section_name}}章节，项目名称：{{project_name}}"
    result = svc.render(template, section_name="施工组织设计", project_name="测试项目")
    assert "施工组织设计" in result
    assert "测试项目" in result


def test_eval_fact_consistency():
    result = eval_fact_consistency(
        "本项目位于北京，工期180天",
        ["北京", "180天", "甲方单位"],
    )
    assert result.score == pytest.approx(2 / 3)


def test_eval_compliance_coverage():
    result = eval_compliance_coverage(
        ["施工组织设计 施工方案 质量保证措施"],
        ["施工方案", "质量保证", "安全措施"],
    )
    assert result.score == pytest.approx(2 / 3)
