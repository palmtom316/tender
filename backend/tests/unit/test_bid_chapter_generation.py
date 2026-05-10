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


def test_generate_quality_chapter_uses_substantial_strategy_sections() -> None:
    conn = _Conn()
    conn.chapter = {
        "id": uuid4(),
        "chapter_code": "10.1",
        "chapter_title": "质量保证措施",
        "volume_type": "technical",
    }
    conn.requirements = [
        {
            "id": uuid4(),
            "title": "质量目标",
            "requirement_text": "质量目标：工程质量合格率100%，满足国家电网公司优质工程验收要求。",
            "source_file": "招标文件.pdf",
            "source_locator": "page:18",
            "priority_level": "normal",
            "is_veto": False,
            "is_hard_constraint": False,
            "source_metadata": {"constraint_subtype": "quality_target"},
        }
    ]

    row = generate_bid_chapter_draft(conn, project_id=uuid4(), chapter_id=conn.chapter["id"])

    assert "## 质量目标响应" in row["content_md"]
    assert "## 质量管理组织" in row["content_md"]
    assert "## 过程质量控制措施" in row["content_md"]
    assert "## 质量检查与闭环改进" in row["content_md"]
    assert "{{chart:quality_system}}" in row["content_md"]


def test_generate_schedule_chapter_uses_progress_strategy_and_chart_placeholder() -> None:
    conn = _Conn()
    conn.chapter = {
        "id": uuid4(),
        "chapter_code": "10.3",
        "chapter_title": "工程进度计划及保证措施",
        "volume_type": "technical",
    }
    conn.requirements = [
        {
            "id": uuid4(),
            "title": "计划工期",
            "requirement_text": "计划工期90日历天，须编制进度保证措施。",
            "source_file": "招标文件.pdf",
            "source_locator": "page:20",
            "priority_level": "normal",
            "is_veto": False,
            "is_hard_constraint": False,
            "source_metadata": {"constraint_subtype": "schedule_target"},
        }
    ]

    row = generate_bid_chapter_draft(conn, project_id=uuid4(), chapter_id=conn.chapter["id"])

    assert "## 里程碑计划" in row["content_md"]
    assert "## 关键路径与资源保障" in row["content_md"]
    assert "## 进度预警与纠偏机制" in row["content_md"]
    assert "{{chart:schedule_gantt}}" in row["content_md"]
