"""Integration test for review workflow and compliance matrix."""

from __future__ import annotations

import pytest

import tender_backend.workflows.review_section  # noqa: F401
from tender_backend.workflows.registry import get_workflow, list_workflows
from tender_backend.services.review_service.review_engine import build_project_review, review_draft, ReviewIssue


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


def test_project_review_flags_pricing_content_and_uncovered_hard_requirement() -> None:
    requirement_id = "11111111-1111-1111-1111-111111111111"

    class _Cursor:
        def __init__(self):
            self.result = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            if "FROM project_requirement" in query:
                self.result = [
                    {
                        "id": requirement_id,
                        "category": "veto",
                        "title": "安全生产许可证",
                        "requirement_text": "必须提供安全生产许可证",
                        "source_text": "必须提供安全生产许可证",
                        "is_veto": True,
                        "is_hard_constraint": True,
                    }
                ]
            elif "FROM chapter_draft" in query:
                self.result = [{"chapter_code": "3.3", "content_md": "本章包含投标报价说明"}]
            elif "FROM bid_chapter WHERE" in query:
                self.result = [{"chapter_code": "3.3", "chapter_title": "硬约束", "volume_type": "technical", "sort_order": 1}]
            elif "FROM bid_chapter_requirement" in query:
                self.result = [{"requirement_id": requirement_id, "chapter_code": "3.3"}]
            elif "FROM requirement_match" in query:
                self.result = []
            return self

        def fetchall(self):
            return self.result

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    issues = build_project_review(_Conn(), project_id=__import__("uuid").UUID("22222222-2222-2222-2222-222222222222"))
    titles = {issue.title for issue in issues}

    assert any("约束未覆盖" in title for title in titles)
    assert "正文包含报价相关内容" in titles
