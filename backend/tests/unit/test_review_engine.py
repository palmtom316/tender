from __future__ import annotations

from tender_backend.services.review_service.review_engine import review_draft
from tender_backend.services.review_service import review_engine


def test_review_draft_rejects_thin_generic_response():
    issues = review_draft(
        content="我方将严格响应招标文件要求。",
        chapter_code="10.1",
        requirements=[],
        facts={},
    )

    assert any(issue.title == "章节内容过短" for issue in issues)
    assert any(issue.title == "章节内容泛化" for issue in issues)


def test_review_draft_requires_strategy_sections_and_chart_placeholders():
    content = """
    ## 编制原则
    ## 质量目标响应
    工程质量合格率100%，满足国网要求。
    """

    issues = review_draft(
        content=content,
        chapter_code="10.1",
        requirements=[{"id": "r1", "category": "technical", "title": "质量目标", "requirement_text": "工程质量合格率100%。"}],
        facts={},
    )

    titles = {issue.title for issue in issues}
    assert "缺少策略必备章节" in titles
    assert "缺少必备图表占位符" in titles


def test_review_draft_accepts_complete_strategy_skeleton():
    content = """
    ## 编制原则
    ## 质量目标响应
    工程质量合格率100%，满足国网要求。
    ## 质量管理组织
    建立项目经理牵头、技术负责人主控的质量管理体系。
    ## 过程质量控制措施
    覆盖材料进场、工序交接、隐蔽工程和关键节点验收。
    ## 质量检查与闭环改进
    通过自检、互检、专检、整改、复验形成闭环。
    {{chart:quality_system}}
    本章还包括资料同步、标准条款响应、责任岗位和检查频次，确保内容充分。
    """

    issues = review_draft(
        content=content,
        chapter_code="10.1",
        requirements=[{"id": "r1", "category": "technical", "title": "质量目标", "requirement_text": "工程质量合格率100%。"}],
        facts={},
    )

    assert not any(issue.title in {"缺少策略必备章节", "缺少必备图表占位符", "章节内容泛化"} for issue in issues)


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.conn.queries.append(query)
        if "FROM project_requirement" in query:
            if self.conn.fail_on_raw_requirements:
                raise AssertionError("raw requirements should not be loaded with confirmed constraint set")
            self.result = []
        elif "FROM chapter_draft" in query:
            self.result = [{"chapter_code": "10.1", "content_md": "## 质量目标响应\n质量目标\n{{chart:quality_system}}"}]
        elif "FROM bid_chapter_requirement" in query:
            self.result = []
        elif "FROM bid_chapter" in query:
            self.result = [{"chapter_code": "10.1", "chapter_title": "质量保证措施", "volume_type": "technical", "sort_order": 1}]
        elif "FROM requirement_match" in query:
            self.result = []
        elif "FROM chart_asset" in query:
            self.result = [{"placeholder_key": "quality_system", "chart_type": "quality_system", "status": "draft"}]
        else:
            self.result = []
        return self

    def fetchall(self):
        return self.result


class _Conn:
    def __init__(self):
        self.queries = []
        self.fail_on_raw_requirements = True

    def cursor(self, *args, **kwargs):
        return _Cursor(self)


def test_build_project_review_prefers_confirmed_constraints_and_flags_unapproved_charts(monkeypatch):
    from uuid import uuid4

    constraint_id = uuid4()

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {
                "id": uuid4(),
                "version": 1,
                "status": "confirmed",
                "items": [
                    {
                        "id": constraint_id,
                        "category": "technical",
                        "constraint_subtype": "quality_target",
                        "title": "质量目标",
                        "constraint_text": "质量目标",
                        "metadata_json": {"mapped_chapter_codes": ["10.1"]},
                    }
                ],
            }

    monkeypatch.setattr(review_engine, "TenderConstraintService", _ConstraintService)

    issues = review_engine.build_project_review(_Conn(), project_id=uuid4())

    assert any(issue.title == "引用图表未审批" for issue in issues)
    assert not any(issue.title.startswith("硬约束未映射章节") for issue in issues)
