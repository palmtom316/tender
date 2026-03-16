"""Integration test for review workflow and compliance matrix."""

from __future__ import annotations

import pytest

import tender_backend.workflows.review_section  # noqa: F401
from tender_backend.workflows.registry import get_workflow, list_workflows
from tender_backend.services.review_service.review_engine import review_draft, ReviewIssue


def test_review_section_workflow_registered():
    assert "review_section" in list_workflows()


def test_review_section_has_expected_steps():
    wf_cls = get_workflow("review_section")
    wf = wf_cls()
    step_names = [s.name for s in wf.steps]
    assert step_names == [
        "load_drafts",
        "load_review_context",
        "rule_review",
        "model_review",
        "build_compliance_matrix",
        "persist_issues",
    ]


def test_review_detects_uncovered_veto():
    issues = review_draft(
        content="施工组织设计内容",
        chapter_code="CH01",
        requirements=[
            {"category": "veto", "title": "安全生产许可证"},
        ],
        facts={},
    )
    p0 = [i for i in issues if i.severity == "P0"]
    assert len(p0) >= 1
    assert "安全生产许可证" in p0[0].title


def test_review_detects_short_content():
    issues = review_draft(
        content="太短了",
        chapter_code="CH01",
        requirements=[],
        facts={},
    )
    p1 = [i for i in issues if i.severity == "P1"]
    assert len(p1) >= 1
    assert "过短" in p1[0].title


def test_review_detects_fact_inconsistency():
    issues = review_draft(
        content="本项目工期为365天" * 20,  # make it long enough
        chapter_code="CH01",
        requirements=[],
        facts={"project_location": "上海市浦东新区"},
    )
    p2 = [i for i in issues if i.severity == "P2"]
    assert len(p2) >= 1
