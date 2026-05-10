from tender_backend.services.technical_bid_writer import TechnicalBidWriter


def test_technical_self_check_flags_pricing_terms() -> None:
    result = TechnicalBidWriter()._self_check("## 响应内容\n本章不应出现投标报价。")

    assert result["has_response_section"] is True
    assert result["contains_pricing_terms"] is True


def test_technical_self_check_detects_strategy_sections_and_chart_placeholders() -> None:
    result = TechnicalBidWriter()._self_check(
        """
        ## 编制原则
        ## 质量目标响应
        ## 质量管理组织
        ## 过程质量控制措施
        ## 质量检查与闭环改进
        {{chart:quality_system}}
        """
    )

    assert result["has_strategy_sections"] is True
    assert result["strategy_section_count"] == 4
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
                "strategy": {"key": "quality_assurance"},
            }

    class _ChartService:
        def generate_spec(self, *, chart_type, title, placeholder_key=None, context=None):
            return {"placeholder_key": placeholder_key, "nodes": ["质量负责人", "施工班组"]}

        def create_or_update(self, conn, *, project_id, chart_type, title, spec_json, outline_node_id=None):
            created_charts.append((chart_type, title, spec_json, outline_node_id))
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
    assert "{{chart:quality_system}}" in result["draft"]["content_md"]
    assert captured["prompt_inputs"]["strategy"]["key"] == "quality_assurance"
    assert captured["metadata"]["context_hash"]
    assert captured["metadata"]["self_check"]["chart_placeholder_count"] == 1
