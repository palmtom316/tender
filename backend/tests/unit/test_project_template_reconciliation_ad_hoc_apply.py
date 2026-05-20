from __future__ import annotations

from uuid import uuid4

from psycopg.types.json import Jsonb

from tender_backend.api.project_template_instances import _apply_ad_hoc_add_chapter_suggestions_to_bid_outline
from tender_backend.services.template_directory_reconciliation_service import DirectoryReconciliationSuggestion


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.conn.queries.append((query, params))
        if "FROM bid_outline" in query:
            self.result = {"id": self.conn.outline_id}
        elif "FROM bid_chapter" in query and "ORDER BY sort_order" in query:
            self.result = None
        elif "COALESCE(MAX(sort_order)" in query:
            self.result = {"next_sort_order": 120}
        elif "INSERT INTO bid_chapter_requirement" in query:
            self.result = {"id": params[0]}
        elif "INSERT INTO bid_chapter" in query:
            self.conn.inserted_chapter_id = params[0]
            self.result = {"id": params[0]}
        else:
            self.result = None
        return self

    def fetchone(self):
        return self.result


class _Conn:
    def __init__(self):
        self.outline_id = uuid4()
        self.queries = []
        self.inserted_chapter_id = None

    def cursor(self, *args, **kwargs):
        return _Cursor(self)


def test_apply_ad_hoc_add_chapter_suggestion_materializes_bid_chapter_marker_and_mapping() -> None:
    project_id = uuid4()
    requirement_id = uuid4()
    suggestion = DirectoryReconciliationSuggestion(
        id="s1",
        suggestion_type="add_chapter",
        severity="critical",
        source_type="tender_document",
        skippable=False,
        required_code="99",
        required_title="施工现场总平面布置专项方案",
        payload={
            "ad_hoc_required": True,
            "template_match_status": "missing",
            "suggested_initial_status": "task_card_pending",
            "requirement_id": str(requirement_id),
            "volume_type": "technical",
        },
    )
    conn = _Conn()

    _apply_ad_hoc_add_chapter_suggestions_to_bid_outline(conn, project_id=project_id, suggestions=[suggestion])

    insert_query, insert_params = next((query, params) for query, params in conn.queries if "INSERT INTO bid_chapter" in query)
    assert "metadata_json" in insert_query
    assert insert_params[3] == "99"
    assert insert_params[4] == "施工现场总平面布置专项方案"
    assert insert_params[5] == "technical"
    assert isinstance(insert_params[8], Jsonb)
    assert insert_params[8].obj["ad_hoc_required"] is True
    assert insert_params[8].obj["template_match_status"] == "missing"
    mapping_params = next(params for query, params in conn.queries if "INSERT INTO bid_chapter_requirement" in query)
    assert mapping_params[1] == conn.inserted_chapter_id
    assert mapping_params[2] == requirement_id
