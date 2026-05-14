from uuid import uuid4

from tender_backend.services.review_service.review_engine import ReviewIssue, classify_review_issue_route


def test_review_issue_source_classification_routes_template_causes_to_template_workspace():
    issue = ReviewIssue(severity="P1", title="模板占位符缺失", detail="placeholder missing", metadata_json={"issue_source": "template_placeholder"})
    route = classify_review_issue_route(issue)
    assert route["issue_source"] == "template_placeholder"
    assert route["suggested_workspace"] == "template"


def test_review_issue_source_classification_routes_content_causes_to_editor_workspace():
    issue = ReviewIssue(severity="P2", title="正文事实错误", detail="bad fact", metadata_json={"issue_source": "generated_content"})
    route = classify_review_issue_route(issue)
    assert route["issue_source"] == "generated_content"
    assert route["suggested_workspace"] == "editor"


def test_review_issue_source_classification_handles_seal_and_requirement_sources():
    requirement_id = str(uuid4())
    issue = ReviewIssue(severity="P0", title="未响应条款", detail="missing", requirement_id=requirement_id, metadata_json={})
    route = classify_review_issue_route(issue)
    assert route["issue_source"] == "requirement_not_responded"
    assert route["suggested_workspace"] == "template"
