from __future__ import annotations

from uuid import uuid4

from tender_backend.api import template_bindings


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.conn.queries.append((query, params))
        if "SELECT metadata_json FROM project" in query:
            self.result = [{"metadata_json": {"legacy_pre_constraint_set": True}}]
        elif "UPDATE project" in query:
            self.conn.updated_metadata = params[0].obj
            self.result = []
        return self

    def fetchone(self):
        return self.result[0] if self.result else None


class _Conn:
    def __init__(self):
        self.queries = []
        self.updated_metadata = None
        self.committed = False

    def cursor(self, *args, **kwargs):
        return _Cursor(self)

    def commit(self):
        self.committed = True


def test_persist_template_render_status_updates_project_metadata() -> None:
    conn = _Conn()
    project_id = uuid4()

    template_bindings._persist_template_render_status(
        conn,
        project_id=project_id,
        result={
            "required_failed_count": 2,
            "failed_count": 3,
            "items": [
                {"filename": "a.docx", "required": True, "status": "failed", "error": "missing field"},
                {"filename": "b.docx", "required": False, "status": "failed", "error": "optional"},
            ],
        },
    )

    assert conn.updated_metadata["legacy_pre_constraint_set"] is True
    status = conn.updated_metadata["template_render_status"]
    assert status["required_failed_count"] == 2
    assert status["failed_count"] == 3
    assert status["failed_required_items"] == ["a.docx"]
    assert conn.committed is True
