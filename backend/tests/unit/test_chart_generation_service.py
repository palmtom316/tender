import json
from uuid import uuid4

from tender_backend.services.chart_generation_service import (
    ChartGenerationService,
    _chart_spec_system_prompt,
    _generate_spec_with_ai,
    _prepare_payload,
    default_chart_spec,
)
from tender_backend.db.repositories.chart_asset_repo import ChartAssetRepository
from tender_backend.services.chart_service.redactor import redact_context_for_chart, scan_blind_bid_keywords


def test_org_chart_requires_nodes() -> None:
    result = ChartGenerationService().validate(chart_type="org_chart", spec_json={})

    assert result["valid"] is False
    assert result["issues"]


def test_render_svg_accepts_string_and_object_nodes() -> None:
    svg = ChartGenerationService().render_svg(
        title="项目组织机构图",
        spec_json={"nodes": ["项目经理", {"label": "安全负责人"}]},
    )

    assert "项目组织机构图" in svg
    assert "项目经理" in svg
    assert "安全负责人" in svg


def test_chart_context_redactor_removes_blind_bid_sensitive_values() -> None:
    context = {
        "chapter": {"chapter_code": "10.2"},
        "tender_summary": {
            "project_name": "重庆市区配网改造",
            "project_location": "重庆市渝中区",
            "tenderer": "国网重庆电力",
            "tender_no": "SGCC-2026-001",
        },
        "personnel_selections": [
            {"snapshot_json": {"name": "张三", "certificate_no": "ABC123", "role": "安全负责人"}},
        ],
        "company_assets": {
            "company_profiles": [{"company_name": "REDACTED", "profile_json": {"platform": "REDACTED"}}],
            "performances": [{"project_name": "重庆10kV示范工程", "client_name": "国网重庆电力"}],
        },
    }

    redacted = redact_context_for_chart(context, is_blind_bid=True)
    rendered = str(redacted)

    assert "张三" not in rendered
    assert "ABC123" not in rendered
    assert "REDACTED" not in rendered
    assert "重庆市渝中区" not in rendered
    assert "SGCC-2026-001" not in rendered
    assert "安全负责人" in rendered


def test_blind_bid_keyword_scan_detects_sensitive_spec_labels() -> None:
    issues = scan_blind_bid_keywords(
        {
            "chart_type": "quality_system",
            "title": "REDACTED质量体系图",
            "nodes": [{"id": "manager", "label": "张三"}],
            "edges": [],
        },
        blacklist=["REDACTED", "张三"],
    )

    assert {issue["keyword"] for issue in issues} == {"REDACTED", "张三"}


def test_create_or_update_marks_blind_bid_sensitive_spec_as_needs_review(monkeypatch, tmp_path) -> None:
    rows = []

    class _Repo:
        def create(self, _conn, **kwargs):
            rows.append(kwargs)

            class _Row:
                id = uuid4()
                project_id = kwargs["project_id"]
                outline_node_id = kwargs.get("outline_node_id")
                chart_type = kwargs["chart_type"]
                title = kwargs["title"]
                spec_json = kwargs["spec_json"]
                rendered_svg = kwargs["rendered_svg"]
                rendered_path = None
                placeholder_key = kwargs["placeholder_key"]
                mermaid_source = kwargs["mermaid_source"]
                rendered_png_path = kwargs["rendered_png_path"]
                status = kwargs["status"]
                version = 1
                metadata_json = kwargs["metadata_json"]

                class _Time:
                    def isoformat(self):
                        return "2026-05-11T00:00:00"

                created_at = _Time()
                updated_at = _Time()

            return _Row()

    service = ChartGenerationService(repo=_Repo())
    result = service.create_or_update(
        object(),
        project_id=uuid4(),
        chart_type="quality_system",
        title="质量管理体系图",
        spec_json={
            "placeholder_key": "quality_system",
            "nodes": [{"id": "manager", "label": "张三"}],
            "edges": [],
            "metadata_json": {"is_blind_bid": True, "blind_bid_blacklist": ["张三"]},
        },
    )

    assert result["status"] == "needs_review"
    assert rows[0]["rendered_svg"] is None
    assert "blind_bid_blacklist" not in str(rows[0]["spec_json"])
    assert rows[0]["metadata_json"]["blind_bid_scan"]["issues"][0]["keyword"] == "张三"


def test_blind_bid_blacklist_metadata_is_not_scanned_as_spec_content() -> None:
    issues = scan_blind_bid_keywords({"title": "质量管理体系图", "nodes": []}, ["张三"])

    assert issues == []


def test_generate_spec_with_ai_serializes_uuid_context(monkeypatch) -> None:
    captured = {}

    class _Settings:
        ai_gateway_url = "http://ai-gateway:8100"
        chart_ai_gateway_timeout_seconds = 1.0
        ai_gateway_shared_secret = ""

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"content":"{\\"nodes\\":[]}"}'

    def _urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("tender_backend.services.chart_generation_service.get_settings", lambda: _Settings())
    monkeypatch.setattr("tender_backend.services.chart_generation_service.urllib.request.urlopen", _urlopen)

    result = _generate_spec_with_ai(
        chart_type="risk_matrix",
        title="风险分级管控矩阵",
        placeholder_key="risk_matrix",
        context={"chapter": {"id": uuid4(), "chapter_code": "8"}},
    )

    user_message = captured["payload"]["messages"][1]["content"]
    assert result == {"nodes": []}
    assert '"id": "' in user_message
    assert captured["timeout"] == 1.0


def test_chart_asset_repository_upserts_by_placeholder() -> None:
    queries = []
    project_id = uuid4()

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            queries.append((query, params))
            self.params = params
            return self

        def fetchone(self):
            return {
                "id": uuid4(),
                "project_id": project_id,
                "outline_node_id": None,
                "chart_type": "schedule_gantt",
                "title": "施工进度计划图",
                "spec_json": self.params[5].obj,
                "rendered_svg": "<svg/>",
                "rendered_path": None,
                "placeholder_key": self.params[7],
                "mermaid_source": self.params[8],
                "rendered_png_path": self.params[9],
                "status": self.params[10],
                "version": 2,
                "template_instance_id": None,
                "template_revision_no": None,
                "is_stale_by_template": False,
                "stale_by_template_revision_no": None,
                "stale_by_template_block_id": None,
                "metadata_json": self.params[14].obj,
                "created_at": _Time(),
                "updated_at": _Time(),
            }

    class _Time:
        def isoformat(self):
            return "2026-05-14T00:00:00"

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    result = ChartAssetRepository().create(
        _Conn(),
        project_id=project_id,
        chart_type="schedule_gantt",
        title="施工进度计划图",
        spec_json={"placeholder_key": "schedule_gantt", "source_refs": [{"constraint_id": uuid4()}]},
        rendered_svg="<svg/>",
        rendered_png_path="/tmp/schedule.png",
        placeholder_key="schedule_gantt",
        mermaid_source="gantt",
        status="draft",
        metadata_json={"source_context": {"constraint_id": uuid4()}},
    )

    assert "ON CONFLICT (project_id, placeholder_key)" in queries[0][0]
    assert result.placeholder_key == "schedule_gantt"
    assert isinstance(queries[0][1][5].obj["source_refs"][0]["constraint_id"], str)


def test_create_or_update_marks_default_specs_as_needs_review() -> None:
    rows = []

    class _Repo:
        def create(self, _conn, **kwargs):
            rows.append(kwargs)

            class _Row:
                id = uuid4()
                project_id = kwargs["project_id"]
                outline_node_id = kwargs.get("outline_node_id")
                chart_type = kwargs["chart_type"]
                title = kwargs["title"]
                spec_json = kwargs["spec_json"]
                rendered_svg = kwargs["rendered_svg"]
                rendered_path = None
                placeholder_key = kwargs["placeholder_key"]
                mermaid_source = kwargs["mermaid_source"]
                rendered_png_path = kwargs["rendered_png_path"]
                status = kwargs["status"]
                version = 1
                metadata_json = kwargs["metadata_json"]

                class _Time:
                    def isoformat(self):
                        return "2026-05-11T00:00:00"

                created_at = _Time()
                updated_at = _Time()

            return _Row()

    service = ChartGenerationService(repo=_Repo())
    spec = service.generate_spec(chart_type="indicator_table", title="绿色施工指标表", placeholder_key="indicator_table")
    result = service.create_or_update(
        object(),
        project_id=uuid4(),
        chart_type="indicator_table",
        title="绿色施工指标表",
        spec_json=spec,
    )

    assert result["status"] == "needs_review"
    assert rows[0]["metadata_json"]["source_kind"] == "default_spec"


def test_create_or_update_stamps_template_revision_metadata() -> None:
    rows = []
    template_instance_id = uuid4()

    class _Repo:
        def create(self, _conn, **kwargs):
            rows.append(kwargs)

            class _Row:
                id = uuid4()
                project_id = kwargs["project_id"]
                outline_node_id = kwargs.get("outline_node_id")
                chart_type = kwargs["chart_type"]
                title = kwargs["title"]
                spec_json = kwargs["spec_json"]
                rendered_svg = kwargs["rendered_svg"]
                rendered_path = None
                placeholder_key = kwargs["placeholder_key"]
                mermaid_source = kwargs["mermaid_source"]
                rendered_png_path = kwargs["rendered_png_path"]
                status = kwargs["status"]
                version = 1
                metadata_json = kwargs["metadata_json"]
                template_instance_id = kwargs["template_instance_id"]
                template_revision_no = kwargs["template_revision_no"]
                is_stale_by_template = kwargs["is_stale_by_template"]

                class _Time:
                    def isoformat(self):
                        return "2026-05-11T00:00:00"

                created_at = _Time()
                updated_at = _Time()

            return _Row()

    service = ChartGenerationService(repo=_Repo())
    result = service.create_or_update(
        object(),
        project_id=uuid4(),
        chart_type="indicator_table",
        title="指标台账",
        spec_json={"placeholder_key": "indicator_table", "columns": ["指标"], "rows": [["质量"]]},
        template_instance_id=template_instance_id,
        template_revision_no=12,
    )

    assert rows[0]["template_instance_id"] == template_instance_id
    assert rows[0]["template_revision_no"] == 12
    assert rows[0]["is_stale_by_template"] is False
    assert result["template_revision_no"] == 12


def test_default_schedule_spec_does_not_invent_dates() -> None:
    spec = default_chart_spec(chart_type="schedule_gantt", title="施工进度计划图", placeholder_key="schedule_gantt")

    assert spec["_default_spec"] is True
    assert "tasks" not in spec
    assert spec["columns"] == ["阶段/工序", "计划开始条件", "计划完成条件", "衔接关系", "来源"]
    assert "缺少已确认日期" in spec["fallback_reason"]


def test_create_or_update_blocks_dated_schedule_without_source_trace() -> None:
    rows = []

    class _Repo:
        def create(self, _conn, **kwargs):
            rows.append(kwargs)

            class _Row:
                id = uuid4()
                project_id = kwargs["project_id"]
                outline_node_id = kwargs.get("outline_node_id")
                chart_type = kwargs["chart_type"]
                title = kwargs["title"]
                spec_json = kwargs["spec_json"]
                rendered_svg = kwargs["rendered_svg"]
                rendered_path = None
                placeholder_key = kwargs["placeholder_key"]
                mermaid_source = kwargs["mermaid_source"]
                rendered_png_path = kwargs["rendered_png_path"]
                status = kwargs["status"]
                version = 1
                metadata_json = kwargs["metadata_json"]

                class _Time:
                    def isoformat(self):
                        return "2026-05-11T00:00:00"

                created_at = _Time()
                updated_at = _Time()

            return _Row()

    service = ChartGenerationService(repo=_Repo())
    result = service.create_or_update(
        object(),
        project_id=uuid4(),
        chart_type="schedule_gantt",
        title="施工进度计划图",
        spec_json={
            "placeholder_key": "schedule_gantt",
            "tasks": [{"id": "prepare", "label": "施工准备", "start": "2026-06-01", "end": "2026-06-05"}],
        },
        chapter_code="10.3",
    )

    assert result["status"] == "needs_review"
    assert rows[0]["rendered_svg"] is None
    assert rows[0]["metadata_json"]["provenance"]["issues"][0]["code"] == "missing_source_trace"
    assert rows[0]["metadata_json"]["source_context"]["chapter_code"] == "10.3"


def test_create_or_update_allows_dated_schedule_with_source_trace(monkeypatch) -> None:
    rows = []

    class _Repo:
        def create(self, _conn, **kwargs):
            rows.append(kwargs)

            class _Row:
                id = uuid4()
                project_id = kwargs["project_id"]
                outline_node_id = kwargs.get("outline_node_id")
                chart_type = kwargs["chart_type"]
                title = kwargs["title"]
                spec_json = kwargs["spec_json"]
                rendered_svg = kwargs["rendered_svg"]
                rendered_path = None
                placeholder_key = kwargs["placeholder_key"]
                mermaid_source = kwargs["mermaid_source"]
                rendered_png_path = kwargs["rendered_png_path"]
                status = kwargs["status"]
                version = 1
                metadata_json = kwargs["metadata_json"]

                class _Time:
                    def isoformat(self):
                        return "2026-05-11T00:00:00"

                created_at = _Time()
                updated_at = _Time()

            return _Row()

    monkeypatch.setattr("tender_backend.services.chart_generation_service.svg_to_png", lambda _svg, path: path)
    service = ChartGenerationService(repo=_Repo())
    result = service.create_or_update(
        object(),
        project_id=uuid4(),
        chart_type="schedule_gantt",
        title="施工进度计划图",
        spec_json={
            "placeholder_key": "schedule_gantt",
            "tasks": [
                {
                    "id": "prepare",
                    "label": "施工准备",
                    "start": "2026-06-01",
                    "end": "2026-06-05",
                    "source_refs": [{"constraint_id": "c-1"}],
                }
            ],
            "source_refs": [{"constraint_id": "c-1"}],
        },
        chapter_code="10.3",
    )

    assert result["status"] == "draft"
    assert rows[0]["rendered_svg"]
    assert rows[0]["metadata_json"]["source_context"]["source_refs"] == [{"constraint_id": "c-1"}]
    assert rows[0]["metadata_json"]["source_context"]["nested_source_refs"] == [[{"constraint_id": "c-1"}]]


def test_chart_spec_system_prompt_includes_json_example_and_source_rules() -> None:
    prompt = _chart_spec_system_prompt("schedule_gantt")

    assert "合法 json object" in prompt
    assert "source_refs" in prompt
    assert "constraint_id" in prompt
    assert "缺少来源时不要输出甘特图任务" in prompt


def test_create_or_update_populates_caption_and_chapter_metadata(monkeypatch) -> None:
    rows = []

    class _Repo:
        def create(self, _conn, **kwargs):
            rows.append(kwargs)

            class _Row:
                id = uuid4()
                project_id = kwargs["project_id"]
                outline_node_id = kwargs.get("outline_node_id")
                chart_type = kwargs["chart_type"]
                title = kwargs["title"]
                spec_json = kwargs["spec_json"]
                rendered_svg = kwargs["rendered_svg"]
                rendered_path = None
                placeholder_key = kwargs["placeholder_key"]
                mermaid_source = kwargs["mermaid_source"]
                rendered_png_path = kwargs["rendered_png_path"]
                status = kwargs["status"]
                version = 1
                metadata_json = kwargs["metadata_json"]

                class _Time:
                    def isoformat(self):
                        return "2026-05-11T00:00:00"

                created_at = _Time()
                updated_at = _Time()

            return _Row()

    monkeypatch.setattr("tender_backend.services.chart_generation_service.svg_to_png", lambda _svg, path: path)
    service = ChartGenerationService(repo=_Repo())
    result = service.create_or_update(
        object(),
        project_id=uuid4(),
        chart_type="indicator_table",
        title="绿色施工指标表",
        spec_json={"placeholder_key": "indicator_table", "columns": ["指标"], "rows": [{"cells": ["节水"]}]},
        chapter_code="10.2",
    )

    assert result["status"] == "draft"
    assert rows[0]["spec_json"]["caption_title"] == "绿色施工指标表"
    assert rows[0]["spec_json"]["chapter_code"] == "10.2"
    assert rows[0]["metadata_json"]["source_context"]["chapter_code"] == "10.2"


def test_create_or_update_keeps_flow_chapter_code_in_source_context(monkeypatch) -> None:
    rows = []

    class _Repo:
        def create(self, _conn, **kwargs):
            rows.append(kwargs)

            class _Row:
                id = uuid4()
                project_id = kwargs["project_id"]
                outline_node_id = kwargs.get("outline_node_id")
                chart_type = kwargs["chart_type"]
                title = kwargs["title"]
                spec_json = kwargs["spec_json"]
                rendered_svg = kwargs["rendered_svg"]
                rendered_path = None
                placeholder_key = kwargs["placeholder_key"]
                mermaid_source = kwargs["mermaid_source"]
                rendered_png_path = kwargs["rendered_png_path"]
                status = kwargs["status"]
                version = 1
                metadata_json = kwargs["metadata_json"]

                class _Time:
                    def isoformat(self):
                        return "2026-05-11T00:00:00"

                created_at = _Time()
                updated_at = _Time()

            return _Row()

    monkeypatch.setattr("tender_backend.services.chart_generation_service.svg_to_png", lambda _svg, path: path)
    service = ChartGenerationService(repo=_Repo())
    result = service.create_or_update(
        object(),
        project_id=uuid4(),
        chart_type="quality_system",
        title="质量管理体系图",
        spec_json={
            "placeholder_key": "quality_system",
            "nodes": [{"id": "manager", "label": "项目经理"}, {"id": "quality", "label": "质量负责人", "parent": "manager"}],
        },
        chapter_code="10.1",
    )

    assert result["status"] == "draft"
    assert rows[0]["metadata_json"]["source_context"]["chapter_code"] == "10.1"


def test_prepare_payload_preserves_flow_parent_for_layout() -> None:
    payload = _prepare_payload(
        chart_type="org_chart",
        title="项目组织机构图",
        spec_json={"nodes": [{"id": "manager", "label": "项目经理"}, {"id": "quality", "label": "质量负责人", "parent": "manager"}]},
    )

    assert payload["nodes"][1]["parent"] == "manager"


def test_prepare_payload_uses_parent_hierarchy_instead_of_linear_edges() -> None:
    payload = _prepare_payload(
        chart_type="org_chart",
        title="项目组织机构图",
        spec_json={
            "nodes": [
                {"id": "manager", "label": "项目经理"},
                {"id": "quality", "label": "质量负责人", "parent": "manager"},
                {"id": "safety", "label": "安全负责人", "parent": "manager"},
            ]
        },
    )

    assert payload["edges"] == [
        {"from": "manager", "to": "quality"},
        {"from": "manager", "to": "safety"},
    ]
