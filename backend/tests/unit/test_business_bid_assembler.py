from uuid import uuid4

from tender_backend.services.business_bid_assembler import BusinessBidAssembler


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.queries.append(query)
        if "FROM bid_outline" in query:
            self.result = [{"id": self.conn.outline_id, "project_id": self.conn.project_id, "status": "confirmed"}]
        elif "FROM bid_chapter" in query:
            self.result = [
                {
                    "id": uuid4(),
                    "chapter_code": "1.1",
                    "chapter_title": "法定资格与资质响应",
                    "volume_type": "qualification",
                    "sort_order": 1,
                    "outline_md": "",
                    "metadata_json": {},
                }
            ]
        elif "INSERT INTO bid_generation_run" in query:
            self.result = [{"id": uuid4(), "status": params[5], "metadata_json": params[6].obj}]
        elif "FROM tender_constraint_item" in query:
            self.result = self.conn.constraint_items
        elif "FROM requirement_match" in query:
            self.result = []
        elif "FROM bid_chapter_requirement" in query:
            raise AssertionError("raw bid_chapter_requirement/project_requirement matrix should not be queried")
        elif "JOIN project_requirement" in query:
            raise AssertionError("raw project_requirement join should not be queried")
        else:
            self.result = []
        return self

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


class _Conn:
    def __init__(self):
        self.project_id = uuid4()
        self.outline_id = uuid4()
        self.constraint_items = [
            {
                "id": uuid4(),
                "requirement_id": uuid4(),
                "category": "qualification",
                "title": "资质要求",
                "constraint_text": "须具备电力工程施工总承包二级及以上资质。",
                "source_file": "招标文件.docx",
                "source_locator": "p3",
                "metadata_json": {"constraint_subtype": "qualification_certificate"},
            }
        ]
        self.committed = False

    def cursor(self, *args, **kwargs):
        return _Cursor(self)

    def commit(self):
        self.committed = True


def test_business_bid_assembly_uses_confirmed_constraints_for_response_matrix(monkeypatch):
    conn = _Conn()

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {"id": uuid4(), "version": 1, "status": "confirmed", "items": conn.constraint_items}

    monkeypatch.setattr("tender_backend.services.business_bid_assembler.TenderConstraintService", _ConstraintService)

    result = BusinessBidAssembler().assemble(conn, project_id=conn.project_id)

    assert result["response_matrix"][0]["source_constraint_id"] == str(conn.constraint_items[0]["id"])
    assert result["response_matrix"][0]["requirement_title"] == "资质要求"
    assert result["run"]["metadata_json"]["constraint_source_of_truth"] == "confirmed_constraint_set"
