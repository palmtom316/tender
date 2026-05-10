from __future__ import annotations

from uuid import uuid4

from tender_backend.services.bid_chapter_generation import generate_bid_chapter_draft
from tender_backend.services.technical_chapter_strategies import strategy_for_chapter


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
                "referenced_chart_keys": params[5] if len(params) > 5 else [],
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
        self.queries = []

    def cursor(self, *args, **kwargs):
        return _Cursor(self)

    def commit(self):
        return None


def test_generate_bid_chapter_draft_excludes_pricing_body() -> None:
    conn = _Conn()
    row = generate_bid_chapter_draft(conn, project_id=uuid4(), chapter_id=conn.chapter["id"])

    assert row["chapter_code"] == "1"
    assert row["volume_type"] == "technical"
    assert "该项属于非本系统处理范围" in row["content_md"]
    assert "投标报价不得写入技术文件" not in row["content_md"]
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


def test_generate_quality_chapter_expands_measures_responsibilities_standards_and_innovation() -> None:
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

    content = row["content_md"]
    assert "### 管控措施" in content
    assert "### 责任分工" in content
    assert "### 标准与验收" in content
    assert "### 风险预控" in content
    assert "### 创新提升" in content
    assert "质量问题销项看板" in content
    assert "首件样板引路" in content


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


def test_generate_bid_chapter_draft_persists_referenced_chart_keys() -> None:
    conn = _Conn()
    conn.chapter = {
        "id": uuid4(),
        "chapter_code": "10.1",
        "chapter_title": "质量保证措施",
        "volume_type": "technical",
    }
    conn.requirements = []
    conn.matches = []

    generate_bid_chapter_draft(conn, project_id=uuid4(), chapter_id=conn.chapter["id"])

    insert_query, insert_params = conn.queries[-1]
    assert "referenced_chart_keys" in insert_query
    assert insert_params[-1] == ["quality_system"]
    assert conn.saved["referenced_chart_keys"] == ["quality_system"]


def test_generate_bid_chapter_draft_can_render_from_normalized_context() -> None:
    conn = _Conn()
    context = {
        "chapter": {
            "id": conn.chapter["id"],
            "chapter_code": "10.2",
            "chapter_title": "安全和绿色施工保障措施",
            "volume_type": "technical",
        },
        "constraints": [
            {
                "id": uuid4(),
                "requirement_id": uuid4(),
                "title": "安全文明施工",
                "constraint_text": "须落实安全文明施工和绿色施工措施。",
                "source_file": "招标文件.pdf",
                "source_locator": "p21",
                "category": "technical",
                "constraint_subtype": "safety_civilized",
            }
        ],
        "standard_clauses": [
            {
                "requirement_id": None,
                "match_status": "matched",
                "matched_title": "安全管理",
                "standard_name": "国家电网安全施工标准",
            }
        ],
        "recommended_charts": ["safety_system", "risk_matrix"],
    }

    row = generate_bid_chapter_draft(conn, project_id=uuid4(), context=context)

    assert "## 安全文明施工目标" in row["content_md"]
    assert "安全文明施工和绿色施工措施" in row["content_md"]
    assert "{{chart:safety_system}}" in row["content_md"]
    assert "{{chart:risk_matrix}}" in row["content_md"]
    assert conn.saved["referenced_chart_keys"] == ["risk_matrix", "safety_system"]


def test_chapter_8_strategy_registers_fifteen_internal_subsections() -> None:
    strategy = strategy_for_chapter("8")

    assert strategy is not None
    assert strategy.key == "construction_plan_and_technical_measures"
    assert len(strategy.sections) == 15
    assert [heading for heading, _body in strategy.sections][:4] == [
        "8.1 编制依据与标准",
        "8.2 工程概况与施工重难点分析",
        "8.3 施工组织与部署",
        "8.4 主要施工方法及技术要求",
    ]
    assert strategy.sections[-1][0] == "8.15 国网年度框架施工工程投标其他创新内容"


def test_chapter_8_child_strategies_match_template_titles() -> None:
    expected = {
        "8.1": "编制依据与标准",
        "8.2": "工程概况与施工重难点分析",
        "8.3": "施工组织与部署",
        "8.4": "主要施工方法及技术要求",
        "8.5": "质量管理体系与措施",
        "8.6": "安全管理体系与措施",
        "8.7": "施工进度计划与保障",
        "8.8": "环境保护、绿色低碳与碳足迹管理",
        "8.9": "科技创新与智能化应用",
        "8.10": "地域特性专题方案",
        "8.11": "竣工验收与数字化移交",
        "8.12": "售后服务、培训及增值服务",
        "8.13": "拟投入施工车辆、机具、工器具、检测设备、安全工器具及设施",
        "8.14": "施工项目部组织架构创新设计",
        "8.15": "国网年度框架施工工程投标其他创新内容",
    }

    for chapter_code, title in expected.items():
        strategy = strategy_for_chapter(chapter_code)
        assert strategy is not None
        assert strategy.sections[0][0] == title


def test_generate_chapter_8_renders_fifteen_subsections_without_promoting_to_top_level() -> None:
    conn = _Conn()
    conn.chapter = {
        "id": uuid4(),
        "chapter_code": "8",
        "chapter_title": "施工方案与技术措施",
        "volume_type": "technical",
    }
    conn.requirements = [
        {
            "id": uuid4(),
            "title": "施工方案",
            "requirement_text": "须编制施工组织、主要施工方法、质量安全进度保障和国网工程技术措施。",
            "source_file": "招标文件.pdf",
            "source_locator": "page:22",
            "priority_level": "normal",
            "is_veto": False,
            "is_hard_constraint": False,
            "source_metadata": {"constraint_subtype": "construction_method"},
        }
    ]

    row = generate_bid_chapter_draft(conn, project_id=uuid4(), chapter_id=conn.chapter["id"])

    content = row["content_md"]
    assert "# 8 施工方案与技术措施" in content
    assert "## 8.1 编制依据与标准" in content
    assert "## 8.15 国网年度框架施工工程投标其他创新内容" in content
    assert content.count("\n## 8.") == 15
    assert "重庆主城区" not in content
    assert "行业第一" not in content
    assert "得分点指引" not in content
    assert "### 标准与验收" in content
    assert "{{chart:construction_flow}}" in content
    assert "risk_matrix" in row["referenced_chart_keys"]
