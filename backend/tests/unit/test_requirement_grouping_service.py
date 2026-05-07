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
