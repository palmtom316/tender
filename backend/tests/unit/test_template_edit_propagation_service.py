from __future__ import annotations

from uuid import uuid4

from tender_backend.services.template_edit_propagation_service import TemplateEditPropagationService


class _Cursor:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple | None]] = []
        self.result: list[dict] = []
        self.rowcount = 0
        self.export_count = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query: str, params: tuple | None = None):
        self.queries.append((query, params))
        if "FROM export_record" in query:
            self.result = [{"count": self.export_count}]
            self.rowcount = 1
        elif "FROM project_template_chapter" in query:
            self.result = [{"id": params[0], "volume_type": "technical", "chapter_code": "10.1"}]
            self.rowcount = 1
        elif "UPDATE chapter_draft" in query:
            self.result = []
            self.rowcount = 1
        elif "UPDATE chart_asset" in query:
            self.result = []
            self.rowcount = 2
        else:
            self.result = []
            self.rowcount = 0
        return self

    def fetchone(self):
        return self.result[0] if self.result else None


class _Conn:
    def __init__(self) -> None:
        self.cursor_obj = _Cursor()

    def cursor(self, *args, **kwargs):
        return self.cursor_obj


class _Block:
    def __init__(self, block_type: str, placeholder_key: str | None = None) -> None:
        self.id = uuid4()
        self.project_id = uuid4()
        self.template_chapter_id = uuid4()
        self.block_type = block_type
        self.label = block_type
        self.placeholder_key = placeholder_key


def test_ai_prompt_edit_marks_matching_chapter_draft_stale_by_template() -> None:
    conn = _Conn()
    block = _Block("ai_prompt")

    impact = TemplateEditPropagationService().apply_stale_impact(conn, block=block, revision_no=7, actor="Dev User")

    assert impact["stale_drafts"] == 1
    assert impact["stale_charts"] == 0
    assert impact["stale_docx"] == 1
    assert impact["stale_draft_count"] == 1
    update_query = next(query for query, _params in conn.cursor_obj.queries if "UPDATE chapter_draft" in query)
    assert "is_stale_by_template = true" in update_query
    assert "template_stale_reason" in update_query
    assert "stale_by_template_block_id" in update_query
    assert "is_stale = true" not in update_query
    assert "\n                        stale_reason =" not in update_query
    assert "COALESCE(is_stale_by_template, false) = false" not in update_query


def test_chart_prompt_edit_marks_matching_chart_assets_stale_by_template() -> None:
    conn = _Conn()
    block = _Block("chart_prompt", placeholder_key="quality_system")

    impact = TemplateEditPropagationService().apply_stale_impact(conn, block=block, revision_no=8, actor="Dev User")

    assert impact["stale_drafts"] == 0
    assert impact["stale_charts"] == 2
    assert impact["stale_docx"] == 1
    assert impact["stale_chart_count"] == 2
    update_query = next(query for query, _params in conn.cursor_obj.queries if "UPDATE chart_asset" in query)
    assert "is_stale_by_template = true" in update_query
    assert "stale_by_template_block_id" in update_query
    assert "template_stale_reason" in update_query
    assert "chapter_code" in update_query
    assert "COALESCE(is_stale_by_template, false) = false" not in update_query


def test_chart_prompt_without_placeholder_is_scoped_to_chapter() -> None:
    conn = _Conn()
    block = _Block("chart_prompt", placeholder_key=None)

    TemplateEditPropagationService().apply_stale_impact(conn, block=block, revision_no=8, actor="Dev User")

    update_query, update_params = next((query, params) for query, params in conn.cursor_obj.queries if "UPDATE chart_asset" in query)
    assert "project_id = %s" in update_query
    assert "chapter_code" in update_query
    assert "placeholder_key = %s" not in update_query
    assert "chart_type = %s" not in update_query
    assert update_params[-2:] == ("10.1", "10.1")


def test_page_format_edit_only_marks_docx_render_stale() -> None:
    conn = _Conn()
    block = _Block("page_format")

    impact = TemplateEditPropagationService().apply_stale_impact(conn, block=block, revision_no=9, actor="Dev User")

    assert impact["stale_drafts"] == 0
    assert impact["stale_charts"] == 0
    assert impact["stale_docx"] == 1
    assert impact["stale_export_artifact_count"] == 1
    assert not any("UPDATE chapter_draft" in query for query, _params in conn.cursor_obj.queries)
    assert not any("UPDATE chart_asset" in query for query, _params in conn.cursor_obj.queries)


def test_docx_impact_counts_completed_exports() -> None:
    conn = _Conn()
    conn.cursor_obj.export_count = 3
    block = _Block("page_format")

    impact = TemplateEditPropagationService().apply_stale_impact(conn, block=block, revision_no=9, actor="Dev User")

    assert impact["stale_docx"] == 3
    assert impact["stale_export_artifact_count"] == 3
    export_query = next(query for query, _params in conn.cursor_obj.queries if "FROM export_record" in query)
    assert "status = 'completed'" in export_query
