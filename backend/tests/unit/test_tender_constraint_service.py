from uuid import uuid4

from tender_backend.services.tender_constraint_service import TenderConstraintService


class _Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self.queries.append((query, params))
        self.current = self.responses.pop(0)
        return self

    def fetchone(self):
        return self.current[0] if self.current else None

    def fetchall(self):
        return self.current


class _Conn:
    def __init__(self, responses):
        self.cursor_obj = _Cursor(responses)
        self.committed = False

    def cursor(self, row_factory=None):
        return self.cursor_obj

    def commit(self):
        self.committed = True


def test_latest_confirmed_returns_confirmed_set_and_accepted_items_only():
    project_id = uuid4()
    set_id = uuid4()
    accepted_item = {
        "id": uuid4(),
        "constraint_set_id": set_id,
        "project_id": project_id,
        "category": "technical",
        "status": "accepted",
        "confirmation_level": "auto_accept",
        "title": "质量目标",
        "constraint_text": "质量目标合格率100%。",
        "metadata_json": {"constraint_subtype": "quality_target"},
    }
    conn = _Conn(
        [
            [{"id": set_id, "project_id": project_id, "version": 3, "status": "confirmed"}],
            [accepted_item],
        ]
    )

    result = TenderConstraintService().latest_confirmed(conn, project_id=project_id)

    assert result["id"] == set_id
    assert result["status"] == "confirmed"
    assert result["items"] == [accepted_item]
    item_query, item_params = conn.cursor_obj.queries[1]
    assert "status IN ('accepted', 'confirmed')" in item_query
    assert item_params == (set_id,)


def test_build_from_requirements_copies_constraint_subtype_metadata():
    project_id = uuid4()
    requirement_id = uuid4()
    set_id = uuid4()
    item_id = uuid4()
    requirement = {
        "id": requirement_id,
        "project_id": project_id,
        "category": "technical",
        "title": "质量目标",
        "requirement_text": "质量目标合格率100%。",
        "source_text": "质量目标合格率100%。",
        "source_file": "招标文件.docx",
        "source_locator": "p1",
        "confidence": 0.92,
        "human_confirmed": False,
        "requires_human_confirm": False,
        "ignored_for_pricing": False,
        "is_veto": False,
        "is_hard_constraint": False,
        "review_status": "pending",
        "source_metadata": {
            "scope_policy": "bid_writing_v1",
            "constraint_subtype": "quality_target",
        },
        "created_at": "now",
    }
    conn = _Conn(
        [
            [{"version": 1}],
            [requirement],
            [{"id": set_id, "project_id": project_id, "version": 1, "status": "draft"}],
            [
                {
                    "id": item_id,
                    "constraint_set_id": set_id,
                    "project_id": project_id,
                    "requirement_id": requirement_id,
                    "category": "technical",
                    "status": "accepted",
                    "metadata_json": {"constraint_subtype": "quality_target"},
                }
            ],
        ]
    )

    result = TenderConstraintService().build_from_requirements(conn, project_id=project_id)

    assert result["items"][0]["id"] == item_id
    insert_query, insert_params = conn.cursor_obj.queries[3]
    assert "INSERT INTO tender_constraint_item" in insert_query
    assert "constraint_subtype" in insert_query
    metadata = insert_params[-1].obj
    assert metadata["scope_policy"] == "bid_writing_v1"
    assert metadata["constraint_subtype"] == "quality_target"
    assert "quality_target" in insert_params


def test_latest_confirmed_selects_constraint_subtype_column():
    project_id = uuid4()
    set_id = uuid4()
    accepted_item = {
        "id": uuid4(),
        "constraint_set_id": set_id,
        "project_id": project_id,
        "category": "technical",
        "constraint_subtype": "quality_target",
        "status": "accepted",
        "confirmation_level": "auto_accept",
        "title": "质量目标",
        "constraint_text": "质量目标合格率100%。",
        "metadata_json": {},
    }
    conn = _Conn(
        [
            [{"id": set_id, "project_id": project_id, "version": 3, "status": "confirmed"}],
            [accepted_item],
        ]
    )

    result = TenderConstraintService().latest_confirmed(conn, project_id=project_id)

    assert result["items"][0]["constraint_subtype"] == "quality_target"
    item_query, _ = conn.cursor_obj.queries[1]
    assert "constraint_subtype" in item_query
