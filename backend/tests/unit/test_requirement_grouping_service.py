from uuid import uuid4

from tender_backend.services.requirement_grouping_service import build_requirement_workbench


def _req(**overrides):
    data = {
        "id": uuid4(),
        "category": "technical",
        "title": "技术要求",
        "requirement_text": "按技术规范编制施工方案。",
        "source_text": "按技术规范编制施工方案。",
        "source_file": "招标文件.docx",
        "source_locator": "p1",
        "confidence": 0.92,
        "human_confirmed": False,
        "requires_human_confirm": False,
        "ignored_for_pricing": False,
        "is_veto": False,
        "is_hard_constraint": False,
        "review_status": "pending",
    }
    data.update(overrides)
    return data


def test_ordinary_technical_clause_is_auto_accepted_sampling():
    result = build_requirement_workbench("project-1", [_req()])

    assert result["stats"]["auto_accept_count"] == 1
    package = result["packages"][0]
    assert package["confirmation_level"] == "auto_accept"
    assert package["lane"] == "sampling"
    assert package["blocking"] is False


def test_key_field_conflict_is_critical_and_not_silently_merged():
    req_a = _req(
        category="format",
        title="正副本份数",
        requirement_text="投标文件正本1份，副本2份。",
        source_text="投标文件正本1份，副本2份。",
    )
    req_b = _req(
        category="format",
        title="正副本份数",
        requirement_text="投标文件正本2份，副本4份。",
        source_text="投标文件正本2份，副本4份。",
    )

    result = build_requirement_workbench("project-1", [req_a, req_b])

    package = result["packages"][0]
    assert package["confirmation_level"] == "critical"
    assert package["blocking"] is True
    assert package["has_conflict"] is True
    assert "copy_count" in package["conflict_fields"]
    assert package["source_count"] == 2


def test_personnel_certificate_grade_conflict_is_detected():
    req_a = _req(
        category="project_team",
        title="项目经理资格",
        requirement_text="项目经理须具备机电工程一级注册建造师资格。",
        source_metadata={"constraint_subtype": "personnel_certificate"},
    )
    req_b = _req(
        category="project_team",
        title="项目经理资格",
        requirement_text="项目经理须具备机电工程二级注册建造师资格。",
        source_metadata={"constraint_subtype": "personnel_certificate"},
    )

    package = build_requirement_workbench("project-1", [req_a, req_b])["packages"][0]

    assert package["has_conflict"] is True
    assert "certificate_grade" in package["conflict_fields"]
    assert package["confirmation_level"] == "critical"


def test_schedule_duration_conflict_is_detected():
    req_a = _req(category="schedule", title="计划工期", requirement_text="计划工期90日历天。")
    req_b = _req(category="schedule", title="计划工期", requirement_text="计划工期120日历天。")

    package = build_requirement_workbench("project-1", [req_a, req_b])["packages"][0]

    assert package["has_conflict"] is True
    assert "duration" in package["conflict_fields"]
    assert package["key_fields"]["duration"] == ["120日历天", "90日历天"]


def test_signature_seal_conflict_is_detected():
    req_a = _req(category="format", title="签章要求", requirement_text="投标文件须法定代表人签字并加盖公章。")
    req_b = _req(category="format", title="签章要求", requirement_text="投标文件仅需电子签章。")

    package = build_requirement_workbench("project-1", [req_a, req_b])["packages"][0]

    assert package["has_conflict"] is True
    assert "signature_seal" in package["conflict_fields"]


def test_performance_quality_file_count_and_deadline_conflicts_are_detected():
    result = build_requirement_workbench(
        "project-1",
        [
            _req(category="performance", title="业绩要求", requirement_text="近三年须具有2项类似工程业绩。"),
            _req(category="performance", title="业绩要求", requirement_text="近三年须具有3项类似工程业绩。"),
            _req(category="technical", title="质量目标", requirement_text="质量目标合格率100%。", source_metadata={"constraint_subtype": "quality_target"}),
            _req(category="technical", title="质量目标", requirement_text="质量目标优良。", source_metadata={"constraint_subtype": "quality_target"}),
            _req(category="format", title="文件份数", requirement_text="电子版1份。"),
            _req(category="format", title="文件份数", requirement_text="电子版2份。"),
            _req(category="format", title="递交截止", requirement_text="递交截止时间为2026年6月1日09:00。"),
            _req(category="format", title="递交截止", requirement_text="递交截止时间为2026年6月2日09:00。"),
        ],
    )

    conflict_fields = {
        field
        for package in result["packages"]
        for field in package["conflict_fields"]
    }

    assert {"performance_count", "quality_target", "file_count", "date"} <= conflict_fields


def test_pricing_only_clause_is_ignored():
    result = build_requirement_workbench(
        "project-1",
        [
            _req(
                category="business",
                title="报价要求",
                requirement_text="投标报价不得超过最高限价100万元。",
                ignored_for_pricing=True,
            )
        ],
    )

    package = result["packages"][0]
    assert package["confirmation_level"] == "ignored"
    assert package["lane"] == "ignored"


def test_technical_constraints_are_grouped_by_bid_writing_subtype():
    result = build_requirement_workbench(
        "project-1",
        [
            _req(
                id="quality",
                requirement_text="质量目标：工程质量合格率100%，满足国家电网公司验收要求。",
                source_metadata={"constraint_subtype": "quality_target"},
            ),
            _req(
                id="schedule",
                requirement_text="计划工期90日历天，须编制进度保证措施。",
                source_metadata={"constraint_subtype": "schedule_target"},
            ),
            _req(
                id="safety",
                requirement_text="须落实安全文明施工、绿色施工和风险管控措施。",
                source_metadata={"constraint_subtype": "safety_civilized"},
            ),
            _req(
                id="personnel",
                category="project_team",
                requirement_text="项目经理1名，须具备机电工程一级注册建造师资格。",
                source_metadata={"constraint_subtype": "personnel_count"},
            ),
        ],
    )

    topics = {package["topic"] for package in result["packages"]}

    assert topics == {"quality_target", "schedule_target", "safety_civilized", "personnel_count"}
    assert result["stats"]["package_count"] == 4
