from __future__ import annotations

from uuid import uuid4

from tender_backend.services.technical_chapter_context import TechnicalChapterContextBuilder


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.conn.queries.append(query)
        if "FROM bid_chapter" in query and "WHERE id" in query:
            self.result = [self.conn.chapter]
        elif "FROM tender_summary" in query:
            self.result = [self.conn.summary] if self.conn.summary else []
        elif "FROM tender_constraint_set" in query:
            self.result = [self.conn.constraint_set] if self.conn.constraint_set else []
        elif "FROM tender_constraint_item" in query:
            self.result = self.conn.constraint_items
        elif "FROM scoring_criteria" in query:
            self.result = self.conn.scoring
        elif "FROM requirement_match" in query:
            self.result = self.conn.standard_matches
        elif "FROM project_personnel_selection" in query:
            self.result = self.conn.personnel
        elif "FROM project_equipment_selection" in query:
            self.result = self.conn.equipment
        elif "FROM chart_asset" in query:
            self.result = self.conn.charts
        elif "FROM company_profile" in query:
            self.result = self.conn.company_profiles
        elif "FROM qualification_certificate" in query:
            self.result = self.conn.certificates
        elif "FROM project_performance" in query:
            self.result = self.conn.performances
        elif "FROM evidence_asset" in query:
            self.result = self.conn.evidence_assets
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
        self.chapter_id = uuid4()
        self.constraint_id = uuid4()
        self.requirement_id = uuid4()
        self.chapter = {
            "id": self.chapter_id,
            "project_id": self.project_id,
            "chapter_code": "10.1",
            "chapter_title": "质量保证措施",
            "volume_type": "technical",
            "metadata_json": {"requirement_count": 1},
        }
        self.summary = {
            "project_name": "配网改造工程",
            "project_location": "重庆",
            "construction_period": "90日历天",
            "quality_requirement": "合格率100%",
            "bid_deadline": "2026-06-01",
            "tenderer": "国网重庆电力",
            "raw_facts_json": {"voltage_level": "10kV"},
        }
        self.constraint_set = {"id": uuid4(), "version": 3, "status": "confirmed"}
        self.constraint_items = [
            {
                "id": self.constraint_id,
                "requirement_id": self.requirement_id,
                "category": "technical",
                "constraint_subtype": "quality_target",
                "title": "质量目标",
                "constraint_text": "工程质量合格率100%。",
                "source_file": "招标文件.pdf",
                "source_locator": "p18",
                "metadata_json": {"mapped_chapter_code": "10.1"},
            }
        ]
        self.scoring = [
            {
                "id": uuid4(),
                "dimension": "质量保证措施",
                "max_score": 10,
                "scoring_method": "措施完整得满分",
                "sub_items_json": [{"name": "质量体系", "score": 5}],
                "source_locator": "p30",
            }
        ]
        self.standard_matches = [
            {
                "id": uuid4(),
                "requirement_id": self.requirement_id,
                "match_status": "matched",
                "matched_source_type": "standard_clause",
                "matched_source_id": uuid4(),
                "matched_title": "质量验收",
                "evidence_summary": "应按国网质量验收要求闭环。",
                "clause_no": "5.1",
                "clause_title": "质量管理",
                "clause_text": "施工质量应全过程控制。",
                "standard_name": "国家电网施工质量标准",
                "standard_code": "Q/GDW",
            }
        ]
        self.personnel = [{"id": uuid4(), "intended_role": "质量负责人", "snapshot_json": {"name": "张三"}, "confirmed": True}]
        self.equipment = [{"id": uuid4(), "asset_type": "tool", "intended_role": "质量检测", "snapshot_json": {"name": "接地电阻测试仪"}, "confirmed": True}]
        self.charts = [{"id": uuid4(), "chart_type": "quality_system", "placeholder_key": "quality_system", "title": "质量管理体系图", "status": "draft"}]
        self.company_profiles = [
            {"id": uuid4(), "company_name": "REDACTED", "business_scope": "输变电工程施工", "profile_json": {"strength": "国网项目经验"}}
        ]
        self.certificates = [
            {"id": uuid4(), "certificate_name": "电力工程施工总承包", "grade": "二级", "specialty": "电力工程", "valid_to": "2027-12-31", "status": "active"}
        ]
        self.performances = [
            {"id": uuid4(), "project_name": "10kV配网改造", "client_name": "国网重庆电力", "service_scope": "配网施工", "evidence_summary": "已完成验收"}
        ]
        self.evidence_assets = [
            {"id": uuid4(), "asset_name": "质量体系认证证书", "asset_domain": "qualification", "asset_type": "certificate", "file_name": "quality.pdf"}
        ]
        self.queries = []

    def cursor(self, *args, **kwargs):
        return _Cursor(self)


def test_technical_chapter_context_builder_collects_traceable_inputs():
    conn = _Conn()

    context = TechnicalChapterContextBuilder().build(conn, project_id=conn.project_id, chapter_id=conn.chapter_id)

    assert context["chapter"]["chapter_code"] == "10.1"
    assert context["constraint_set"]["version"] == 3
    assert context["constraints"][0]["constraint_subtype"] == "quality_target"
    assert context["tender_summary"]["quality_requirement"] == "合格率100%"
    assert context["scoring_items"][0]["dimension"] == "质量保证措施"
    assert context["standard_clauses"][0]["standard_name"] == "国家电网施工质量标准"
    assert context["personnel_selections"][0]["snapshot_json"]["name"] == "张三"
    assert context["equipment_selections"][0]["snapshot_json"]["name"] == "接地电阻测试仪"
    assert context["company_assets"]["company_profiles"][0]["company_name"] == "REDACTED"
    assert context["company_assets"]["certificates"][0]["certificate_name"] == "电力工程施工总承包"
    assert context["company_assets"]["performances"][0]["project_name"] == "10kV配网改造"
    assert context["company_assets"]["evidence_assets"][0]["asset_name"] == "质量体系认证证书"
    assert context["chart_assets"][0]["placeholder_key"] == "quality_system"
    assert context["recommended_charts"] == ["quality_system"]


def test_technical_chapter_context_builder_handles_empty_optional_data():
    conn = _Conn()
    conn.summary = None
    conn.constraint_items = []
    conn.scoring = []
    conn.standard_matches = []
    conn.personnel = []
    conn.equipment = []
    conn.charts = []
    conn.company_profiles = []
    conn.certificates = []
    conn.performances = []
    conn.evidence_assets = []

    context = TechnicalChapterContextBuilder().build(conn, project_id=conn.project_id, chapter_id=conn.chapter_id)

    assert context["tender_summary"] == {}
    assert context["constraints"] == []
    assert context["standard_clauses"] == []
    assert context["company_assets"]["company_profiles"] == []
    assert context["recommended_charts"] == ["quality_system"]
