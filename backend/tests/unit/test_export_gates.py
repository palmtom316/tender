from datetime import datetime
from uuid import uuid4

from tender_backend.api.exports import _referenced_chart_placeholders, _unapproved_referenced_chart_count
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


def test_chart_gate_counts_only_unapproved_referenced_assets():
    assets = [
        _asset(placeholder_key="quality_system", status="approved"),
        _asset(placeholder_key="schedule_gantt", status="draft"),
        _asset(placeholder_key="unused_chart", status="draft"),
    ]

    assert _unapproved_referenced_chart_count(assets, {"quality_system", "schedule_gantt"}) == 1
    assert _unapproved_referenced_chart_count(assets, set()) == 0
