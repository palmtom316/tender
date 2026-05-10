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

    assert state == {
        "format_passed": False,
        "format_status": "warning_not_checked",
        "format_message": "格式校验尚未接入自动检查，导出前需人工复核。",
    }


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
