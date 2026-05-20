import asyncio
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tender_backend.api import exports
from tender_backend.core.security import CurrentUser, Role
from tender_backend.services.export_gate_service import (
    build_export_gate_state,
    _format_gate_state,
    _referenced_chart_placeholders,
    _unapproved_referenced_chart_count,
)
from tender_backend.db.repositories.chart_asset_repo import ChartAssetRow


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.query = query
        self.params = params
        return self

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.cursor_obj = _Cursor(rows)

    def cursor(self, row_factory=None):
        return self.cursor_obj


def _asset(*, placeholder_key: str, status: str) -> ChartAssetRow:
    now = datetime.utcnow()
    return ChartAssetRow(
        id=uuid4(),
        project_id=uuid4(),
        outline_node_id=None,
        chart_type=placeholder_key,
        title=placeholder_key,
        spec_json={},
        rendered_svg=None,
        rendered_path=None,
        placeholder_key=placeholder_key,
        mermaid_source=None,
        rendered_png_path=None,
        status=status,
        version=1,
        template_instance_id=None,
        template_revision_no=None,
        is_stale_by_template=False,
        stale_by_template_revision_no=None,
        stale_by_template_block_id=None,
        template_stale_reason=None,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


def test_referenced_chart_placeholders_are_scanned_from_current_drafts():
    project_id = uuid4()
    conn = _Conn(
        [
            {"content_md": "## 图表\n{{chart:quality_system}}\n{{chart:schedule_gantt}}"},
            {"content_md": "重复引用 {{chart:quality_system}}"},
            {"content_md": "无图表"},
        ]
    )

    result = _referenced_chart_placeholders(conn, project_id=project_id)

    assert result == {"quality_system", "schedule_gantt"}
    assert conn.cursor_obj.params == (project_id,)


def test_referenced_chart_placeholders_prefers_persisted_reference_keys():
    project_id = uuid4()
    conn = _Conn(
        [
            {
                "content_md": "过期正文 {{chart:old_scan_key}}",
                "referenced_chart_keys": ["quality_system", "schedule_gantt"],
            },
            {"content_md": "无图表", "referenced_chart_keys": []},
        ]
    )

    result = _referenced_chart_placeholders(conn, project_id=project_id)

    assert result == {"quality_system", "schedule_gantt"}


def test_chart_gate_counts_only_unapproved_referenced_assets():
    assets = [
        _asset(placeholder_key="quality_system", status="approved"),
        _asset(placeholder_key="schedule_gantt", status="draft"),
        _asset(placeholder_key="unused_chart", status="draft"),
    ]

    assert _unapproved_referenced_chart_count(assets, {"quality_system", "schedule_gantt"}) == 1
    assert _unapproved_referenced_chart_count(assets, set()) == 0


def test_format_gate_warning_state_is_not_reported_as_passed():
    state = _format_gate_state()

    assert state["format_passed"] is False
    assert state["format_status"] == "warning_not_checked"
    assert state["format_message"] == "格式校验尚未接入自动检查，导出前需人工复核。"
    assert state["format_issue_count"] == 0
    assert state["format_issues"] == []


def test_format_gate_reads_latest_export_record_check_result():
    project_id = uuid4()

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.params = params
            self.result = [
                {
                    "metadata_json": {
                        "render_evidence": {
                            "format_check": {
                                "format_passed": False,
                                "format_status": "failed",
                                "format_message": "发现 1 项格式问题。",
                                "issues": [{"code": "table_missing_borders", "severity": "P1"}],
                            }
                        }
                    }
                }
            ]
            return self

        def fetchone(self):
            return self.result[0]

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    state = _format_gate_state(_Conn(), project_id=project_id)

    assert state["format_passed"] is False
    assert state["format_status"] == "failed"
    assert state["format_issue_count"] == 1
    assert state["format_issues"][0]["code"] == "table_missing_borders"


def test_export_gate_blocks_without_confirmed_constraint_set_for_non_legacy(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return None

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.result = [{"metadata_json": {}}] if "FROM project" in query else []
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

        def fetchall(self):
            return self.result

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["constraints_confirmed"] is False
    assert state["can_export"] is False


def test_export_gate_blocks_required_template_render_failures_and_stale_artifacts(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"id": uuid4(), "version": 1, "status": "confirmed", "items": []}

        def latest(self, conn, *, project_id):
            return {"id": uuid4(), "version": 1, "status": "confirmed", "items": []}

    class _Cursor:
        def __init__(self):
            self.result = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            if "FROM project" in query:
                self.result = [
                    {
                        "metadata_json": {
                            "template_render_status": {
                                "required_failed_count": 2,
                                "failed_required_items": ["资质证明", "授权书"],
                            }
                        }
                    }
                ]
            elif "FROM chapter_draft" in query and "content_md" in query:
                self.result = []
            elif "AS count" in query:
                self.result = [{"count": 3}]
            else:
                self.result = []
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

        def fetchall(self):
            return self.result

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["template_required_items_rendered"] is False
    assert state["gates"]["required_template_failed_count"] == 2
    assert state["gates"]["stale_artifacts_clear"] is False
    assert state["gates"]["stale_artifact_count"] == 3
    assert state["can_export"] is False


def test_export_gate_reports_template_stale_artifacts(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"id": uuid4(), "version": 1, "status": "confirmed", "items": []}

        def latest(self, conn, *, project_id):
            return {"id": uuid4(), "version": 1, "status": "confirmed", "items": []}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            if "FROM project" in query:
                self.result = [{"metadata_json": {}}]
            elif "FROM chapter_draft" in query and "content_md" in query:
                self.result = []
            elif "stale_template_artifact_count" in query:
                self.result = [{"stale_template_artifact_count": 2}]
            elif "AS count" in query:
                self.result = [{"count": 0}]
            else:
                self.result = []
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

        def fetchall(self):
            return self.result

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["template_stale_artifacts_clear"] is False
    assert state["gates"]["stale_template_artifact_count"] == 2
    assert state["can_export"] is False


def test_export_gate_blocks_unresolved_critical_constraint_items(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"id": uuid4(), "version": 2, "status": "confirmed", "items": []}

        def latest(self, conn, *, project_id):
            return {
                "id": uuid4(),
                "version": 2,
                "status": "confirmed",
                "items": [
                    {
                        "id": uuid4(),
                        "status": "needs_review",
                        "confirmation_level": "critical",
                        "metadata_json": {"has_conflict": True},
                    }
                ],
            }

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.result = [{"metadata_json": {}}] if "FROM project" in query else [{"count": 0}] if "AS count" in query else []
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

        def fetchall(self):
            return self.result

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["critical_constraints_resolved"] is False
    assert state["gates"]["unresolved_critical_constraint_count"] == 1
    assert state["can_export"] is False


def test_create_export_blocks_when_final_gate_fails(monkeypatch):
    project_id = uuid4()

    class _AccessCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.result = [{"id": project_id}] if "SELECT id FROM project" in query else []
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _AccessCursor()

    monkeypatch.setattr(
        exports,
        "build_export_gate_state",
        lambda conn, *, project_id: {
            "can_export": False,
            "gates": {"constraints_confirmed": False},
        },
    )
    monkeypatch.setattr(exports, "render_export", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("render_export should not run")))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            exports.create_export(
                project_id,
                exports.CreateExportBody(mode="single_docx"),
                _Conn(),
                CurrentUser(token="dev-token", role=Role.ADMIN, display_name="Developer"),
            )
        )

    assert exc_info.value.status_code == 409
    assert "export gates block export" in str(exc_info.value.detail)


def test_create_export_writes_actual_pages_back_to_chapter_drafts(monkeypatch, tmp_path):
    project_id = uuid4()
    output_path = tmp_path / "technical.docx"
    output_path.write_bytes(b"fake-docx")
    updates = []

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            if "SELECT id FROM project" in query:
                self.result = [{"id": project_id}]
            elif "UPDATE chapter_draft" in query:
                updates.append((query, params))
                self.result = []
            elif "INSERT INTO export_record" in query:
                self.result = [
                    {
                        "id": uuid4(),
                        "project_id": project_id,
                        "status": "completed",
                        "template_name": "plain_docx",
                        "export_key": str(output_path),
                        "metadata_json": params[5],
                    }
                ]
            else:
                self.result = []
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    monkeypatch.setattr(exports, "build_export_gate_state", lambda conn, *, project_id: {"can_export": True, "gates": {}})
    monkeypatch.setattr(exports, "render_export", lambda conn, *, project_id, mode: str(output_path))
    monkeypatch.setattr(
        exports,
        "inspect_rendered_docx_evidence",
        lambda path: {"path": str(path), "page_count": {"status": "counted", "actual_pages": 95, "method": "test"}},
    )

    result = asyncio.run(
        exports.create_export(
            project_id,
            exports.CreateExportBody(mode="single_docx"),
            _Conn(),
            CurrentUser(token="dev-token", role=Role.ADMIN, display_name="Developer"),
        )
    )

    assert result["status"] == "completed"
    assert len(updates) == 1
    assert "jsonb_set" in updates[0][0]
    assert updates[0][1] == (95, "counted", project_id)


def test_create_export_records_format_check_in_render_evidence(monkeypatch, tmp_path):
    project_id = uuid4()
    output_path = tmp_path / "technical.docx"
    output_path.write_bytes(b"fake-docx")
    inserted_metadata = {}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            if "SELECT id FROM project" in query:
                self.result = [{"id": project_id}]
            elif "INSERT INTO export_record" in query:
                inserted_metadata.update(params[5].obj)
                self.result = [
                    {
                        "id": uuid4(),
                        "project_id": project_id,
                        "status": "completed",
                        "template_name": "plain_docx",
                        "export_key": str(output_path),
                        "metadata_json": params[5],
                    }
                ]
            else:
                self.result = []
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    monkeypatch.setattr(exports, "build_export_gate_state", lambda conn, *, project_id: {"can_export": True, "gates": {}})
    monkeypatch.setattr(exports, "render_export", lambda conn, *, project_id, mode: str(output_path))
    monkeypatch.setattr(exports, "inspect_rendered_docx_evidence", lambda path: {"path": str(path), "page_count": {"status": "unchecked"}})
    monkeypatch.setattr(
        exports,
        "check_docx_format",
        lambda path: {"format_passed": True, "format_status": "passed", "format_message": "格式检查通过。", "issues": []},
    )

    asyncio.run(
        exports.create_export(
            project_id,
            exports.CreateExportBody(mode="single_docx"),
            _Conn(),
            CurrentUser(token="dev-token", role=Role.ADMIN, display_name="Developer"),
        )
    )

    assert inserted_metadata["render_evidence"]["format_check"]["format_passed"] is True
    assert inserted_metadata["render_evidence"]["format_check"]["format_status"] == "passed"



def test_export_gate_blocks_when_page_estimate_below_target(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"items": []}

        def latest(self, conn, *, project_id):
            return {"items": []}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.query = query
            return self

        def fetchone(self):
            if "metadata_json FROM project" in self.query:
                return {"metadata_json": {}}
            if "COUNT(*)" in self.query or " AS count" in self.query:
                return {"count": 0, "stale_template_artifact_count": 0}
            return None

        def fetchall(self):
            if "FROM chapter_draft" in self.query:
                return [
                    {
                        "content_md": "# 8",
                        "referenced_chart_keys": [],
                        "chapter_code": "8",
                        "target_pages": 100,
                        "estimated_pages": 65,
                        "page_estimate_json": {},
                        "coverage_report_json": {"coverage_passed": True, "issues": []},
                        "chart_closure_report_json": {"chart_closure_passed": True, "issues": []},
                    }
                ]
            return []

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["page_count_passed"] is False
    assert state["gates"]["page_count_status"] == "failed_estimate_below_minimum"
    assert state["can_export"] is False


def test_export_gate_blocks_when_coverage_report_has_p0_issue(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"items": []}

        def latest(self, conn, *, project_id):
            return {"items": []}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.query = query
            return self

        def fetchone(self):
            if "metadata_json FROM project" in self.query:
                return {"metadata_json": {}}
            if "COUNT(*)" in self.query or " AS count" in self.query:
                return {"count": 0, "stale_template_artifact_count": 0}
            return None

        def fetchall(self):
            if "FROM chapter_draft" in self.query:
                return [
                    {
                        "content_md": "# 8",
                        "referenced_chart_keys": [],
                        "chapter_code": "8",
                        "target_pages": 100,
                        "estimated_pages": 95,
                        "page_estimate_json": {},
                        "coverage_report_json": {"coverage_passed": False, "issues": [{"code": "missing_section", "severity": "P0"}]},
                        "chart_closure_report_json": {"chart_closure_passed": True, "issues": []},
                    }
                ]
            return []

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["coverage_passed"] is False
    assert state["gates"]["coverage_issue_count"] == 1
    assert state["can_export"] is False


def test_export_gate_blocks_when_chart_closure_report_has_p0_issue(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"items": []}

        def latest(self, conn, *, project_id):
            return {"items": []}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.query = query
            return self

        def fetchone(self):
            if "metadata_json FROM project" in self.query:
                return {"metadata_json": {}}
            if "COUNT(*)" in self.query or " AS count" in self.query:
                return {"count": 0, "stale_template_artifact_count": 0}
            return None

        def fetchall(self):
            if "FROM chapter_draft" in self.query:
                return [
                    {
                        "content_md": "# 8\n{{chart:construction_flow}}",
                        "referenced_chart_keys": ["construction_flow"],
                        "chapter_code": "8",
                        "target_pages": 100,
                        "estimated_pages": 95,
                        "page_estimate_json": {},
                        "coverage_report_json": {"coverage_passed": True, "issues": []},
                        "chart_closure_report_json": {
                            "chart_closure_passed": False,
                            "issues": [{"code": "chart_placeholder_residual", "chart_key": "construction_flow", "severity": "P0"}],
                        },
                    }
                ]
            return []

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["chart_closure_passed"] is False
    assert state["gates"]["chart_closure_issue_count"] == 1
    assert state["can_export"] is False


def test_export_gate_blocks_pending_ad_hoc_task_card(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"items": []}

        def latest(self, conn, *, project_id):
            return {"items": []}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.query = query
            return self

        def fetchone(self):
            if "metadata_json FROM project" in self.query:
                return {"metadata_json": {}}
            if "COUNT(*)" in self.query or " AS count" in self.query:
                return {"count": 0, "stale_template_artifact_count": 0}
            return None

        def fetchall(self):
            if "FROM bid_chapter" in self.query:
                return [
                    {
                        "chapter_code": "99",
                        "chapter_title": "新增专项方案",
                        "metadata_json": {"ad_hoc_task_card": {"status": "outline_ready"}},
                        "draft_id": None,
                        "coverage_report_json": {},
                    }
                ]
            if "FROM chapter_draft" in self.query:
                return []
            return []

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["ad_hoc_task_cards_ready"] is False
    assert state["gates"]["ad_hoc_task_card_issue_count"] == 1
    assert state["gates"]["ad_hoc_task_card_issues"][0]["message"] == "新增章节任务卡未完成"
    assert "outline_ready" not in state["gates"]["ad_hoc_task_card_issues"][0]["message"]
    assert state["can_export"] is False


def test_export_gate_allows_draft_ready_ad_hoc_task_card(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"items": []}

        def latest(self, conn, *, project_id):
            return {"items": []}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.query = query
            return self

        def fetchone(self):
            if "metadata_json FROM project" in self.query:
                return {"metadata_json": {}}
            if "COUNT(*)" in self.query or " AS count" in self.query:
                return {"count": 0, "stale_template_artifact_count": 0}
            return None

        def fetchall(self):
            if "FROM bid_chapter" in self.query:
                return [
                    {
                        "chapter_code": "99",
                        "chapter_title": "新增专项方案",
                        "metadata_json": {"ad_hoc_task_card": {"status": "draft_ready"}},
                        "draft_id": "draft-99",
                        "coverage_report_json": {"coverage_passed": True},
                    }
                ]
            if "FROM chapter_draft" in self.query:
                return []
            return []

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["ad_hoc_task_cards_ready"] is True
    assert state["can_export"] is True



def test_export_gate_blocks_uninitialized_ad_hoc_required_chapter(monkeypatch):
    project_id = uuid4()

    class _ReqRepo:
        def unconfirmed_veto_count(self, conn, *, project_id):
            return 0

    class _ChartRepo:
        def list_by_project(self, conn, *, project_id):
            return []

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"items": []}

        def latest(self, conn, *, project_id):
            return {"items": []}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            self.query = query
            return self

        def fetchone(self):
            if "metadata_json FROM project" in self.query:
                return {"metadata_json": {}}
            if "COUNT(*)" in self.query or " AS count" in self.query:
                return {"count": 0, "stale_template_artifact_count": 0}
            return None

        def fetchall(self):
            if "FROM bid_chapter" in self.query:
                return [
                    {
                        "chapter_code": "99",
                        "chapter_title": "新增专项方案",
                        "metadata_json": {"ad_hoc_required": True},
                        "draft_id": None,
                        "coverage_report_json": {},
                    }
                ]
            if "FROM chapter_draft" in self.query:
                return []
            return []

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", _ReqRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", _ChartRepo)
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["ad_hoc_task_cards_ready"] is False
    assert state["gates"]["ad_hoc_task_card_issue_count"] == 1
    assert state["can_export"] is False
