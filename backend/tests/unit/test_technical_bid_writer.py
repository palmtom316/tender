from tender_backend.services.technical_bid_writer import TechnicalBidWriter


def test_technical_self_check_flags_pricing_terms() -> None:
    result = TechnicalBidWriter()._self_check("## 响应内容\n本章不应出现投标报价。")

    assert result["has_response_section"] is True
    assert result["contains_pricing_terms"] is True


def test_technical_self_check_detects_strategy_sections_and_chart_placeholders() -> None:
    result = TechnicalBidWriter()._self_check(
        """
        ## 编制原则
        ### 10.1.1 编制依据与质量目标
        ### 10.1.2 质量管理标准和规范
        ### 10.1.3 质量保证体系与组织职责
        ### 10.1.4 全过程质量控制措施
        {{chart:quality_system}}
        """
    )

    assert result["has_strategy_sections"] is True
    assert result["strategy_section_count"] == 4
    assert result["chart_placeholder_count"] == 1


def test_technical_self_check_detects_chapter_8_internal_sections() -> None:
    result = TechnicalBidWriter()._self_check(
        """
        ## 编制原则
        ## 8.1 编制依据与标准
        ## 8.2 工程概况与施工重难点分析
        ## 8.15 国网年度框架施工工程投标其他创新内容
        {{chart:construction_flow}}
        """
    )

    assert result["has_strategy_sections"] is True
    assert result["strategy_section_count"] == 3
    assert result["chart_placeholder_count"] == 1


def test_technical_self_check_detects_chapter_9_work_plan_sections() -> None:
    result = TechnicalBidWriter()._self_check(
        """
        ## 编制原则
        ## 9.1 项目理解与总体工作思路
        ## 9.4 协调配合工作规划
        ## 9.8 跨章节协同与边界管理
        {{chart:responsibility_matrix}}
        """
    )

    assert result["has_strategy_sections"] is True
    assert result["strategy_section_count"] == 3
    assert result["chart_placeholder_count"] == 1


def test_technical_self_check_detects_safety_green_internal_sections() -> None:
    result = TechnicalBidWriter()._self_check(
        """
        ## 编制原则
        ### 10.2.1 安全与绿色施工目标响应
        ### 10.2.4 危险源辨识与风险分级管控
        ### 10.2.7 应急预案体系与响应机制
        {{chart:safety_system}}
        {{chart:risk_matrix}}
        """
    )

    assert result["has_strategy_sections"] is True
    assert result["strategy_section_count"] == 3
    assert result["chart_placeholder_count"] == 2


def test_technical_self_check_detects_schedule_internal_sections() -> None:
    result = TechnicalBidWriter()._self_check(
        """
        ## 编制原则
        ### 10.3.1 编制依据与进度目标
        ### 10.3.5 总体施工进度计划
        ### 10.3.10 进度动态管控与预警纠偏
        {{chart:schedule_gantt}}
        """
    )

    assert result["has_strategy_sections"] is True
    assert result["strategy_section_count"] == 3
    assert result["chart_placeholder_count"] == 1


def test_technical_writer_records_context_and_creates_recommended_charts(monkeypatch) -> None:
    from uuid import uuid4

    project_id = uuid4()
    outline_id = uuid4()
    chapter_id = uuid4()
    created_charts = []
    captured = {}

    class _Writer(TechnicalBidWriter):
        def _confirmed_outline(self, conn, *, project_id):
            return {"id": outline_id, "project_id": project_id, "status": "confirmed"}

        def _chapter(self, conn, *, project_id, chapter_id):
            return {"id": chapter_id, "project_id": project_id, "chapter_code": "10.1", "chapter_title": "质量保证措施", "volume_type": "technical"}

        def _create_run(self, conn, **kwargs):
            captured.update(kwargs)
            return {"id": uuid4(), "prompt_inputs_json": kwargs["prompt_inputs"]}

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {
                "chapter": {"id": chapter_id, "chapter_code": "10.1", "chapter_title": "质量保证措施", "volume_type": "technical"},
                "constraints": [],
                "standard_clauses": [],
                "recommended_charts": ["quality_system"],
                "chart_assets": [],
                "generation_controls": {
                    "target_pages": 80,
                    "target_pages_source": "default",
                    "prompt_overlay_md": "本次生成目标篇幅为 80 页左右 A4。",
                },
                "strategy": {"key": "quality_assurance", "prompt_template_path": "docs/samples/配网质量保证措施提示词.md"},
                "prompt_template": {
                    "path": "docs/samples/配网质量保证措施提示词.md",
                    "status": "loaded",
                    "content_md": "# 国网配网工程技术标第10章第10.1节《质量保证措施》AI编写模板及提示词",
                },
            }

    class _ChartService:
        def generate_spec(self, *, chart_type, title, placeholder_key=None, context=None):
            return {"placeholder_key": placeholder_key, "nodes": ["质量负责人", "施工班组"]}

        def create_or_update(self, conn, *, project_id, chart_type, title, spec_json, outline_node_id=None, chapter_code=None):
            created_charts.append((chart_type, title, spec_json, outline_node_id, chapter_code))
            return {"id": uuid4(), "chart_type": chart_type, "placeholder_key": spec_json["placeholder_key"], "status": "draft"}

    class _Cursor:
        def __init__(self):
            self.result = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            if "INSERT INTO chapter_draft" in query:
                self.result = [
                    {
                        "id": uuid4(),
                        "project_id": params[1],
                        "volume_type": params[2],
                        "chapter_code": params[3],
                        "content_md": params[4],
                        "referenced_chart_keys": params[5],
                    }
                ]
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    monkeypatch.setattr("tender_backend.services.technical_bid_writer.TechnicalChapterContextBuilder", _ContextBuilder)
    monkeypatch.setattr("tender_backend.services.technical_bid_writer.ChartGenerationService", lambda: _ChartService())

    result = _Writer().generate_chapter(_Conn(), project_id=project_id, chapter_id=chapter_id, created_by="Tester")

    assert created_charts[0][0] == "quality_system"
    assert created_charts[0][4] == "10.1"
    assert "{{chart:quality_system}}" in result["draft"]["content_md"]
    assert captured["prompt_inputs"]["strategy"]["key"] == "quality_assurance"
    assert captured["metadata"]["context_hash"]
    assert captured["metadata"]["prompt_contract"]["input_policy"] == "normalized_context_and_strategy_only"
    assert captured["metadata"]["prompt_contract"]["generation_controls"]["target_pages"] == 80
    assert "constraint_ids" in captured["metadata"]["prompt_contract"]["required_output"]["trace_metadata"]
    assert captured["metadata"]["source_trace"]["chart_placeholder_keys"] == ["quality_system"]
    assert captured["metadata"]["self_check"]["chart_placeholder_count"] == 1
    assert captured["metadata"]["prompt_template"]["path"] == "docs/samples/配网质量保证措施提示词.md"
    assert captured["metadata"]["prompt_template"]["status"] == "loaded"
    assert captured["metadata"]["prompt_template"]["content_hash"]


def test_technical_writer_allows_target_pages_override(monkeypatch) -> None:
    from uuid import uuid4

    project_id = uuid4()
    outline_id = uuid4()
    chapter_id = uuid4()
    captured = {}

    class _Writer(TechnicalBidWriter):
        def _confirmed_outline(self, conn, *, project_id):
            return {"id": outline_id, "project_id": project_id, "status": "confirmed"}

        def _chapter(self, conn, *, project_id, chapter_id):
            return {"id": chapter_id, "project_id": project_id, "chapter_code": "10.1", "chapter_title": "质量保证措施", "volume_type": "technical"}

        def _create_run(self, conn, **kwargs):
            captured.update(kwargs)
            return {"id": uuid4(), "prompt_inputs_json": kwargs["prompt_inputs"]}

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {
                "chapter": {"id": chapter_id, "chapter_code": "10.1", "chapter_title": "质量保证措施", "volume_type": "technical"},
                "constraints": [],
                "standard_clauses": [],
                "recommended_charts": [],
                "chart_assets": [],
                "generation_controls": {"target_pages": 80, "target_pages_source": "default"},
                "strategy": {"key": "quality_assurance"},
                "prompt_template": {"status": "loaded", "content_md": "质量提示词"},
            }

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            if "INSERT INTO chapter_draft" in query:
                self.result = [
                    {
                        "id": uuid4(),
                        "project_id": params[1],
                        "volume_type": params[2],
                        "chapter_code": params[3],
                        "content_md": params[4],
                        "referenced_chart_keys": params[5],
                    }
                ]
            return self

        def fetchone(self):
            return self.result[0] if getattr(self, "result", []) else None

    class _Conn:
        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            return None

    monkeypatch.setattr("tender_backend.services.technical_bid_writer.TechnicalChapterContextBuilder", _ContextBuilder)

    _Writer().generate_chapter(_Conn(), project_id=project_id, chapter_id=chapter_id, target_pages=96)

    assert captured["prompt_inputs"]["generation_controls"]["target_pages"] == 96
    assert captured["prompt_inputs"]["generation_controls"]["target_pages_source"] == "request"
    assert "96 页左右 A4" in captured["prompt_inputs"]["generation_controls"]["prompt_overlay_md"]
    assert "质量提示词" in captured["prompt_inputs"]["prompt_template"]["effective_content_md"]
    assert "96 页左右 A4" in captured["prompt_inputs"]["prompt_template"]["effective_content_md"]
