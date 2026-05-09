from __future__ import annotations

from uuid import uuid4

from tender_backend.services.bid_chapter_generation import generate_bid_chapter_draft


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        if "SELECT * FROM bid_chapter WHERE id" in query:
            self.result = [self.conn.chapter]
        elif "FROM bid_chapter_requirement" in query and "JOIN project_requirement" in query:
            self.result = self.conn.requirements
        elif "FROM requirement_match" in query:
            self.result = self.conn.matches
        elif "INSERT INTO chapter_draft" in query:
            self.conn.saved = {
                "id": uuid4(),
                "project_id": params[1],
                "volume_type": params[2],
                "chapter_code": params[3],
                "content_md": params[4],
            }
            self.result = [self.conn.saved]
        else:
            self.result = []
        return self

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


class _Conn:
    def __init__(self):
        self.chapter = {"id": uuid4(), "chapter_code": "1", "chapter_title": "技术偏差表", "volume_type": "technical"}
        self.requirements = [
            {
                "id": uuid4(),
                "title": "不得出现报价",
                "requirement_text": "投标报价不得写入技术文件",
                "source_file": "招标文件.pdf",
                "source_locator": "page:8",
                "priority_level": "hard",
                "is_veto": True,
                "is_hard_constraint": True,
            }
        ]
        self.matches = []
        self.saved = None

    def cursor(self, *args, **kwargs):
        return _Cursor(self)

    def commit(self):
        return None


def test_generate_bid_chapter_draft_excludes_pricing_body() -> None:
    conn = _Conn()
    row = generate_bid_chapter_draft(conn, project_id=uuid4(), chapter_id=conn.chapter["id"])

    assert row["chapter_code"] == "1"
    assert row["volume_type"] == "technical"
    assert "该项涉及报价信息" in row["content_md"]
    assert "硬约束处理" in row["content_md"]
