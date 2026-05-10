from uuid import uuid4

from tender_backend.services.outline_reconciliation_service import OutlineReconciliationService


def test_preview_keeps_template_chapters_without_tender_conflict(monkeypatch):
    project_id = uuid4()
    outline = {
        "id": uuid4(),
        "project_id": project_id,
        "metadata_json": {},
        "chapters": [
            {
                "id": uuid4(),
                "chapter_code": "10.1",
                "chapter_title": "质量保证措施",
                "volume_type": "technical",
                "requirement_ids": [],
                "metadata_json": {"template_key": "sgcc_distribution_technical_v1"},
            }
        ],
    }

    class _Repo:
        def get_latest_by_project(self, conn, *, project_id):
            return outline

    monkeypatch.setattr("tender_backend.services.outline_reconciliation_service.BidOutlineRepository", _Repo)
    monkeypatch.setattr(
        OutlineReconciliationService,
        "_unresolved_critical_requirements",
        lambda self, conn, *, project_id: [],
    )

    preview = OutlineReconciliationService().preview(object(), project_id=project_id)

    assert preview["diffs"][0]["operation"] == "keep_template"
    assert preview["diffs"][0]["reason"] == "无招标文件目录冲突，按用户提供的目录模板保留"
    assert preview["can_confirm"] is True


def test_preview_reports_confirmed_tender_conflict_override(monkeypatch):
    project_id = uuid4()
    outline = {
        "id": uuid4(),
        "project_id": project_id,
        "metadata_json": {},
        "chapters": [
            {
                "id": uuid4(),
                "chapter_code": "13",
                "chapter_title": "技术规范书规定的其他应提交的文件",
                "volume_type": "technical",
                "requirement_ids": [],
                "metadata_json": {
                    "template_key": "sgcc_distribution_technical_v1",
                    "template_conflict": {
                        "policy": "tender_conflict_override",
                        "status": "confirmed",
                        "source_locator": "技术规范书 p12",
                        "proposed_action": "append_required_attachment",
                        "reason": "招标文件要求技术规范响应文件单独成册",
                    },
                },
            }
        ],
    }

    class _Repo:
        def get_latest_by_project(self, conn, *, project_id):
            return outline

    monkeypatch.setattr("tender_backend.services.outline_reconciliation_service.BidOutlineRepository", _Repo)
    monkeypatch.setattr(
        OutlineReconciliationService,
        "_unresolved_critical_requirements",
        lambda self, conn, *, project_id: [],
    )

    preview = OutlineReconciliationService().preview(object(), project_id=project_id)

    diff = preview["diffs"][0]
    assert diff["operation"] == "tender_conflict_override"
    assert diff["source_locator"] == "技术规范书 p12"
    assert diff["proposed_action"] == "append_required_attachment"


def test_unconfirmed_template_conflict_does_not_override_template(monkeypatch):
    project_id = uuid4()
    outline = {
        "id": uuid4(),
        "project_id": project_id,
        "metadata_json": {},
        "chapters": [
            {
                "id": uuid4(),
                "chapter_code": "13",
                "chapter_title": "技术规范书规定的其他应提交的文件",
                "volume_type": "technical",
                "requirement_ids": [],
                "metadata_json": {
                    "template_conflict": {
                        "policy": "tender_conflict_override",
                        "status": "draft",
                        "source_locator": "技术规范书 p12",
                        "proposed_action": "append_required_attachment",
                    }
                },
            }
        ],
    }

    class _Repo:
        def get_latest_by_project(self, conn, *, project_id):
            return outline

    monkeypatch.setattr("tender_backend.services.outline_reconciliation_service.BidOutlineRepository", _Repo)
    monkeypatch.setattr(
        OutlineReconciliationService,
        "_unresolved_critical_requirements",
        lambda self, conn, *, project_id: [],
    )

    preview = OutlineReconciliationService().preview(object(), project_id=project_id)

    assert preview["diffs"][0]["operation"] == "keep_template"


def test_template_conflict_record_requires_rule_based_trigger():
    record = OutlineReconciliationService().build_template_conflict_record(
        source_text="技术投标文件中的施工方案应独立成册、单独密封提交。",
        source_locator="p12",
        affected_chapter_code="8.1",
        proposed_action="separate_volume",
    )

    assert record["policy"] == "tender_conflict_override"
    assert record["status"] == "draft"
    assert record["trigger"] == "separate_volume_submission"
    assert record["source_locator"] == "p12"


def test_template_conflict_record_rejects_ai_only_explanation_without_trigger():
    record = OutlineReconciliationService().build_template_conflict_record(
        source_text="建议优化目录结构以便评审专家阅读。",
        source_locator="ai-note",
        affected_chapter_code="8.1",
        proposed_action="rename_chapter",
    )

    assert record["policy"] == "template_default"
    assert record["status"] == "not_applicable"
    assert record["trigger"] is None
