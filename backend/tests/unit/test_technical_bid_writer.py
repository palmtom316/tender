import json
import re
from uuid import uuid4

import tender_backend.services.technical_bid_writer as technical_bid_writer_module
from tender_backend.services.technical_bid_writer import TechnicalBidWriter, _json_safe


def test_technical_writer_uses_ai_gateway_content_when_available(monkeypatch) -> None:
    project_id = uuid4()
    outline_id = uuid4()
    chapter_id = uuid4()
    captured = {}

    class _Writer(TechnicalBidWriter):
        def _confirmed_outline(self, conn, *, project_id):
            return {"id": outline_id, "project_id": project_id, "status": "confirmed"}

        def _chapter(self, conn, *, project_id, chapter_id):
            return {
                "id": chapter_id,
                "project_id": project_id,
                "chapter_code": "8",
                "chapter_title": "施工方案与技术措施",
                "volume_type": "technical",
            }

        def _create_run(self, conn, **kwargs):
            captured.update(kwargs)
            return {"id": uuid4(), "metadata_json": kwargs["metadata"]}

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {
                "chapter": {
                    "id": chapter_id,
                    "chapter_code": "8",
                    "chapter_title": "施工方案与技术措施",
                    "volume_type": "technical",
                },
                "constraints": [],
                "standard_clauses": [],
                "personnel_selections": [],
                "equipment_selections": [],
                "company_assets": [],
                "recommended_charts": ["construction_flow"],
                "chart_assets": [{"placeholder_key": "construction_flow", "chart_type": "construction_flow"}],
                "generation_controls": {"target_pages": 8, "target_pages_source": "request"},
                "strategy": {"key": "construction_plan_and_technical_measures"},
                "prompt_template": {"status": "loaded", "content_md": "第8章提示词"},
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
    monkeypatch.setattr(
        "tender_backend.services.technical_bid_writer._request_ai_gateway_completion",
        lambda conn, context, rewrite_note=None: {
            "content": "# 8 施工方案与技术措施\n\n## 8.1 编制依据与标准\nDeepSeek 生成正文\n\n{{chart:construction_flow}}",
            "resolved_model": "deepseek-v4-flash",
            "resolved_provider": "deepseek",
            "usage": {"input_tokens": 111, "output_tokens": 222},
        },
        raising=False,
    )

    result = _Writer().generate_chapter(_Conn(), project_id=project_id, chapter_id=chapter_id, target_pages=8)

    assert "DeepSeek 生成正文" in result["draft"]["content_md"]
    assert captured["metadata"]["generation_mode"] == "ai_gateway"
    assert captured["metadata"]["ai_gateway"]["resolved_provider"] == "deepseek"
    assert captured["metadata"]["ai_gateway"]["resolved_model"] == "deepseek-v4-flash"


def test_technical_writer_passes_generate_section_override_to_ai_gateway(monkeypatch) -> None:
    project_id = uuid4()
    outline_id = uuid4()
    chapter_id = uuid4()
    captured = {}

    class _Writer(TechnicalBidWriter):
        def _confirmed_outline(self, conn, *, project_id):
            return {"id": outline_id, "project_id": project_id, "status": "confirmed"}

        def _chapter(self, conn, *, project_id, chapter_id):
            return {
                "id": chapter_id,
                "project_id": project_id,
                "chapter_code": "8",
                "chapter_title": "施工方案与技术措施",
                "volume_type": "technical",
            }

        def _create_run(self, conn, **kwargs):
            captured.update(kwargs)
            return {"id": uuid4(), "metadata_json": kwargs["metadata"]}

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {
                "chapter": {
                    "id": chapter_id,
                    "chapter_code": "8",
                    "chapter_title": "施工方案与技术措施",
                    "volume_type": "technical",
                },
                "constraints": [],
                "standard_clauses": [],
                "personnel_selections": [],
                "equipment_selections": [],
                "company_assets": [],
                "recommended_charts": [],
                "chart_assets": [],
                "generation_controls": {"target_pages": 8, "target_pages_source": "request"},
                "strategy": {"key": "construction_plan_and_technical_measures"},
                "prompt_template": {"status": "loaded", "content_md": "第8章提示词"},
            }

    class _Config:
        enabled = True
        base_url = "https://api.deepseek.com/v1"
        api_key = "sk-generate"
        primary_model = "deepseek-v4-flash"
        fallback_base_url = "https://fallback.example/v1"
        fallback_api_key = "sk-fallback"
        fallback_model = "qwen-plus"

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

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(
                {
                    "content": "# 8 施工方案与技术措施\n\n真实AI正文",
                    "resolved_model": "deepseek-v4-flash",
                    "resolved_provider": "deepseek",
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def _urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    monkeypatch.setattr("tender_backend.services.technical_bid_writer.TechnicalChapterContextBuilder", _ContextBuilder)
    monkeypatch.setattr(
        technical_bid_writer_module,
        "AgentConfigRepository",
        type("_Repo", (), {"get_by_key": lambda self, conn, key: _Config() if key == "generate_section" else None}),
        raising=False,
    )
    monkeypatch.setattr("tender_backend.services.technical_bid_writer.urllib.request.urlopen", _urlopen)

    _Writer().generate_chapter(_Conn(), project_id=project_id, chapter_id=chapter_id, target_pages=8)

    assert captured["payload"]["primary_override"] == {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-generate",
        "model": "deepseek-v4-flash",
    }
    assert captured["payload"]["fallback_override"] == {
        "base_url": "https://fallback.example/v1",
        "api_key": "sk-fallback",
        "model": "qwen-plus",
    }


def test_longform_subsection_rewrite_note_includes_density_hint(monkeypatch) -> None:
    captured = {}

    def fake_completion(_conn, context, rewrite_note=None, task_type=None):
        captured["context"] = context
        captured["rewrite_note"] = rewrite_note
        captured["task_type"] = task_type
        return {
            "content": "正文",
            "resolved_model": "deepseek-v4-flash",
            "resolved_provider": "deepseek",
            "usage": {},
        }

    monkeypatch.setattr(
        "tender_backend.services.technical_bid_writer._request_ai_gateway_completion",
        fake_completion,
        raising=False,
    )

    result = technical_bid_writer_module._request_ai_gateway_subsection_completion(
        None,
        {
            "context": {"recommended_charts": ["quality_system"], "chart_assets": []},
            "section_code": "8.5",
            "section_title": "质量管理体系与措施",
            "target_pages": 10,
            "min_chars": 2300,
            "subsection_density_hint": {
                "expected_chars": 2300,
                "expected_paragraphs": 13,
                "expected_subsections": 6,
            },
            "required_charts": ["quality_system"],
            "required_tables": [],
            "round_index": 1,
        },
    )

    assert result["content"] == "正文"
    assert captured["task_type"] == "generate_longform_subsection"
    assert captured["context"]["longform_subsection"]["subsection_density_hint"]["expected_chars"] == 2300
    assert "展开 6 个独立子专题" in captured["rewrite_note"]
    assert re.search(r"至少\s*13\s*个自然段", captured["rewrite_note"])


def test_technical_writer_routes_large_chapter_8_through_longform_subsection_loop(monkeypatch) -> None:
    project_id = uuid4()
    outline_id = uuid4()
    chapter_id = uuid4()
    captured = {}

    class _Writer(TechnicalBidWriter):
        def _confirmed_outline(self, conn, *, project_id):
            return {"id": outline_id, "project_id": project_id, "status": "confirmed"}

        def _chapter(self, conn, *, project_id, chapter_id):
            return {
                "id": chapter_id,
                "project_id": project_id,
                "chapter_code": "8",
                "chapter_title": "施工方案与技术措施",
                "volume_type": "technical",
            }

        def _create_run(self, conn, **kwargs):
            captured.update(kwargs)
            return {"id": uuid4(), "metadata_json": kwargs["metadata"]}

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {
                "chapter": {"id": chapter_id, "chapter_code": "8", "chapter_title": "施工方案与技术措施", "volume_type": "technical"},
                "constraints": [{"id": uuid4(), "confirmation_level": "normal"}],
                "standard_clauses": [],
                "personnel_selections": [],
                "equipment_selections": [],
                "company_assets": [],
                "recommended_charts": [],
                "chart_assets": [],
                "generation_controls": {"target_pages": 80, "target_pages_source": "default"},
                "strategy": {"key": "construction_plan_and_technical_measures"},
                "prompt_template": {"status": "loaded", "content_md": "第8章提示词"},
            }

    class _LongformSectionGenerator:
        def __init__(self, completion_fn, max_rounds=4):
            self.completion_fn = completion_fn
            self.max_rounds = max_rounds

        def generate_sections(self, context, section_plan, progress_callback=None):
            assert context["generation_controls"]["target_pages"] == 100
            assert section_plan[0]["section_code"] == "8.1"
            return {
                "status": "completed",
                "content_md": "## 8.1 编制依据\n\n长篇分节生成正文",
                "sections": [
                    {
                        "section_code": "8.1",
                        "title": "编制依据",
                        "target_pages": 100,
                        "min_chars": 1,
                        "actual_chars": 8,
                        "status": "completed",
                        "continuation_rounds": 3,
                        "required_charts": [],
                        "required_tables": [],
                        "prompt_hash": "hash-8-1",
                    }
                ],
                "metadata": {"total_input_tokens": 10, "total_output_tokens": 20, "latency_ms": 30},
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
                        "target_pages": params[6],
                        "estimated_pages": params[7],
                        "page_estimate_json": params[8],
                        "coverage_report_json": params[9],
                        "chart_closure_report_json": params[10],
                        "generation_rounds": params[11],
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
    monkeypatch.setattr("tender_backend.services.technical_bid_writer.LongformSectionGenerator", _LongformSectionGenerator, raising=False)
    monkeypatch.setattr(
        "tender_backend.services.technical_bid_writer.plan_chapter_8_sections",
        lambda *, target_pages: [{"section_code": "8.1", "title": "编制依据", "target_pages": target_pages, "min_chars": 1}],
        raising=False,
    )
    monkeypatch.setattr(
        "tender_backend.services.technical_bid_writer._request_ai_gateway_completion",
        lambda context, rewrite_note=None: {"content": "THIS_SINGLE_PASS_CONTENT_MUST_NOT_BE_USED", "usage": {}},
        raising=False,
    )

    result = _Writer().generate_chapter(_Conn(), project_id=project_id, chapter_id=chapter_id, target_pages=100)

    assert result["draft"]["target_pages"] == 100
    assert "## 8.1 编制依据" in result["draft"]["content_md"]
    assert "THIS_SINGLE_PASS_CONTENT_MUST_NOT_BE_USED" not in result["draft"]["content_md"]
    assert result["draft"]["generation_rounds"] == 3
    assert captured["metadata"]["generation_mode"] == "longform_subsection_loop"
    assert captured["metadata"]["ai_gateway"]["longform"]["metadata"]["total_output_tokens"] == 20
    assert captured["metadata"]["ai_gateway"]["longform"]["sections"][0]["section_code"] == "8.1"


def test_technical_writer_reports_longform_progress_for_partial_save(monkeypatch) -> None:
    project_id = uuid4()
    outline_id = uuid4()
    chapter_id = uuid4()
    progress_events = []

    class _Writer(TechnicalBidWriter):
        def _confirmed_outline(self, conn, *, project_id):
            return {"id": outline_id, "project_id": project_id, "status": "confirmed"}

        def _chapter(self, conn, *, project_id, chapter_id):
            return {
                "id": chapter_id,
                "project_id": project_id,
                "chapter_code": "8",
                "chapter_title": "施工方案与技术措施",
                "volume_type": "technical",
            }

        def _create_run(self, conn, **kwargs):
            return {"id": uuid4(), "metadata_json": kwargs["metadata"]}

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {
                "chapter": {"id": chapter_id, "chapter_code": "8", "chapter_title": "施工方案与技术措施", "volume_type": "technical"},
                "constraints": [],
                "standard_clauses": [],
                "personnel_selections": [],
                "equipment_selections": [],
                "company_assets": [],
                "recommended_charts": [],
                "chart_assets": [],
                "generation_controls": {"target_pages": 100, "target_pages_source": "request"},
                "strategy": {"key": "construction_plan_and_technical_measures"},
                "prompt_template": {"status": "loaded", "content_md": "第8章提示词"},
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
                        "target_pages": params[6],
                        "estimated_pages": params[7],
                        "page_estimate_json": params[8],
                        "coverage_report_json": params[9],
                        "chart_closure_report_json": params[10],
                        "generation_rounds": params[11],
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

    class _LongformSectionGenerator:
        def __init__(self, completion_fn, max_rounds=4):
            self.completion_fn = completion_fn

        def generate_sections(self, context, section_plan, progress_callback=None):
            progress_callback(
                {
                    "section_code": "8.1",
                    "title": "编制依据",
                    "completed_sections": 1,
                    "total_sections": 2,
                    "content_md": "## 8.1 编制依据\n\n阶段落稿1",
                    "section_result": {"section_code": "8.1", "status": "completed", "continuation_rounds": 1},
                    "percent": 50,
                }
            )
            progress_callback(
                {
                    "section_code": "8.2",
                    "title": "工程概况",
                    "completed_sections": 2,
                    "total_sections": 2,
                    "content_md": "## 8.1 编制依据\n\n阶段落稿1\n\n## 8.2 工程概况\n\n阶段落稿2",
                    "section_result": {"section_code": "8.2", "status": "completed", "continuation_rounds": 1},
                    "percent": 100,
                }
            )
            return {
                "status": "completed",
                "content_md": "## 8.1 编制依据\n\n阶段落稿1\n\n## 8.2 工程概况\n\n阶段落稿2",
                "sections": [
                    {"section_code": "8.1", "title": "编制依据", "continuation_rounds": 1, "status": "completed"},
                    {"section_code": "8.2", "title": "工程概况", "continuation_rounds": 1, "status": "completed"},
                ],
                "metadata": {"total_input_tokens": 1, "total_output_tokens": 2, "latency_ms": 3},
            }

    monkeypatch.setattr("tender_backend.services.technical_bid_writer.TechnicalChapterContextBuilder", _ContextBuilder)
    monkeypatch.setattr("tender_backend.services.technical_bid_writer.LongformSectionGenerator", _LongformSectionGenerator, raising=False)
    monkeypatch.setattr(
        "tender_backend.services.technical_bid_writer.plan_chapter_8_sections",
        lambda *, target_pages: [
            {"section_code": "8.1", "title": "编制依据", "target_pages": 50, "min_chars": 1},
            {"section_code": "8.2", "title": "工程概况", "target_pages": 50, "min_chars": 1},
        ],
        raising=False,
    )

    _Writer().generate_chapter(
        _Conn(),
        project_id=project_id,
        chapter_id=chapter_id,
        target_pages=100,
        progress_callback=lambda payload: progress_events.append(payload),
    )

    assert [event["completed_sections"] for event in progress_events] == [1, 2]
    assert progress_events[-1]["percent"] == 100
    assert "## 8.2 工程概况" in progress_events[-1]["content_md"]


def test_technical_writer_saves_partial_draft_on_round_progress(monkeypatch) -> None:
    project_id = uuid4()
    outline_id = uuid4()
    chapter_id = uuid4()
    progress_events = []
    saved_contents = []

    class _Writer(TechnicalBidWriter):
        def _confirmed_outline(self, conn, *, project_id):
            return {"id": outline_id, "project_id": project_id, "status": "confirmed"}

        def _chapter(self, conn, *, project_id, chapter_id):
            return {
                "id": chapter_id,
                "project_id": project_id,
                "chapter_code": "8",
                "chapter_title": "施工方案与技术措施",
                "volume_type": "technical",
            }

        def _create_run(self, conn, **kwargs):
            return {"id": uuid4(), "metadata_json": kwargs["metadata"]}

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {
                "chapter": {"id": chapter_id, "chapter_code": "8", "chapter_title": "施工方案与技术措施", "volume_type": "technical"},
                "constraints": [],
                "standard_clauses": [],
                "personnel_selections": [],
                "equipment_selections": [],
                "company_assets": [],
                "recommended_charts": [],
                "chart_assets": [],
                "generation_controls": {"target_pages": 100, "target_pages_source": "request"},
                "strategy": {"key": "construction_plan_and_technical_measures"},
                "prompt_template": {"status": "loaded", "content_md": "第8章提示词"},
            }

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            if "INSERT INTO chapter_draft" in query:
                saved_contents.append(params[4])
                self.result = [
                    {
                        "id": uuid4(),
                        "project_id": params[1],
                        "volume_type": params[2],
                        "chapter_code": params[3],
                        "content_md": params[4],
                        "referenced_chart_keys": params[5],
                        "target_pages": params[6],
                        "estimated_pages": params[7],
                        "page_estimate_json": params[8],
                        "coverage_report_json": params[9],
                        "chart_closure_report_json": params[10],
                        "generation_rounds": params[11],
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

    class _LongformSectionGenerator:
        def __init__(self, completion_fn, max_rounds=4):
            self.completion_fn = completion_fn

        def generate_sections(self, context, section_plan, progress_callback=None):
            progress_callback(
                {
                    "event": "round_started",
                    "section_code": "8.1",
                    "title": "编制依据",
                    "round_index": 1,
                    "max_rounds": 4,
                    "completed_sections": 0,
                    "total_sections": 2,
                    "content_md": "## 8.1 编制依据",
                    "percent": 0,
                }
            )
            progress_callback(
                {
                    "event": "round_progress",
                    "section_code": "8.1",
                    "title": "编制依据",
                    "round_index": 1,
                    "max_rounds": 4,
                    "completed_sections": 0,
                    "total_sections": 2,
                    "content_md": "## 8.1 编制依据\n\n首轮落稿",
                    "percent": 5,
                }
            )
            return {
                "status": "completed",
                "content_md": "## 8.1 编制依据\n\n首轮落稿\n\n## 8.2 工程概况\n\n完成稿",
                "sections": [
                    {"section_code": "8.1", "title": "编制依据", "continuation_rounds": 1, "status": "completed"},
                    {"section_code": "8.2", "title": "工程概况", "continuation_rounds": 1, "status": "completed"},
                ],
                "metadata": {"total_input_tokens": 1, "total_output_tokens": 2, "latency_ms": 3},
            }

    monkeypatch.setattr("tender_backend.services.technical_bid_writer.TechnicalChapterContextBuilder", _ContextBuilder)
    monkeypatch.setattr("tender_backend.services.technical_bid_writer.LongformSectionGenerator", _LongformSectionGenerator, raising=False)
    monkeypatch.setattr(
        "tender_backend.services.technical_bid_writer.plan_chapter_8_sections",
        lambda *, target_pages: [
            {"section_code": "8.1", "title": "编制依据", "target_pages": 50, "min_chars": 1},
            {"section_code": "8.2", "title": "工程概况", "target_pages": 50, "min_chars": 1},
        ],
        raising=False,
    )

    _Writer().generate_chapter(
        _Conn(),
        project_id=project_id,
        chapter_id=chapter_id,
        target_pages=100,
        progress_callback=lambda payload: progress_events.append(payload),
    )

    round_progress = next(event for event in progress_events if event["event"] == "round_progress")
    assert progress_events[0]["event"] == "round_started"
    assert round_progress["completed_sections"] == 0
    assert "首轮落稿" in saved_contents[0]


def test_technical_writer_clears_only_template_stale_state(monkeypatch) -> None:
    project_id = uuid4()
    outline_id = uuid4()
    chapter_id = uuid4()
    queries = []

    class _Writer(TechnicalBidWriter):
        def _confirmed_outline(self, conn, *, project_id):
            return {"id": outline_id, "project_id": project_id, "status": "confirmed"}

        def _chapter(self, conn, *, project_id, chapter_id):
            return {
                "id": chapter_id,
                "project_id": project_id,
                "chapter_code": "8",
                "chapter_title": "施工方案与技术措施",
                "volume_type": "technical",
            }

        def _create_run(self, conn, **kwargs):
            return {"id": uuid4(), "metadata_json": kwargs["metadata"]}

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {
                "chapter": {"id": chapter_id, "chapter_code": "8", "chapter_title": "施工方案与技术措施", "volume_type": "technical"},
                "constraints": [],
                "standard_clauses": [],
                "personnel_selections": [],
                "equipment_selections": [],
                "company_assets": [],
                "recommended_charts": [],
                "chart_assets": [],
                "generation_controls": {"target_pages": 8},
                "strategy": {"key": "construction_plan_and_technical_measures"},
                "prompt_template": {"status": "loaded", "content_md": "第8章提示词"},
            }

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=None):
            queries.append((query, params))
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
    monkeypatch.setattr(
        "tender_backend.services.technical_bid_writer._request_ai_gateway_completion",
        lambda conn, context, rewrite_note=None: {"content": "# 8 施工方案与技术措施\n\n正文", "resolved_model": "deepseek-v4-flash", "resolved_provider": "deepseek", "usage": {}},
        raising=False,
    )

    _Writer().generate_chapter(_Conn(), project_id=project_id, chapter_id=chapter_id, target_pages=8)

    insert_query = next(query for query, _params in queries if "INSERT INTO chapter_draft" in query)
    assert "template_stale_reason = NULL" in insert_query
    assert "is_stale = false" not in insert_query
    assert "\n              stale_reason = NULL" not in insert_query


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
        def generate_spec(self, *, conn=None, chart_type, title, placeholder_key=None, context=None):
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


def test_json_safe_converts_uuids_before_jsonb_insert() -> None:
    value = {"chapter": {"id": uuid4()}, "items": [{"id": uuid4()}]}

    result = _json_safe(value)

    assert isinstance(result["chapter"]["id"], str)
    assert isinstance(result["items"][0]["id"], str)
