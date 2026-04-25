from __future__ import annotations

from types import SimpleNamespace

from tender_backend.services.norm_service.table_requirements import (
    classify_table_strategy,
    deterministic_table_entries_from_block,
    expand_table_rows,
)


def _block(*, title: str, html: str) -> SimpleNamespace:
    return SimpleNamespace(
        table_title=title,
        table_html=html,
        page_start=18,
        page_end=18,
        chapter_label=f"表格: {title}",
        source_refs=["table:t1"],
    )


def test_expand_table_rows_preserves_rowspan_and_colspan_cells() -> None:
    rows = expand_table_rows(
        "<table>"
        "<tr><td rowspan=\"2\">电气强度</td><td colspan=\"2\">标准值</td></tr>"
        "<tr><td>750kV</td><td>≥70kV</td></tr>"
        "</table>"
    )

    assert rows == [
        ["电气强度", "标准值", "标准值"],
        ["电气强度", "750kV", "≥70kV"],
    ]


def test_parameter_limit_table_produces_grouped_requirement_entries() -> None:
    block = _block(
        title="表 4.2.4 变压器内油样性能",
        html=(
            "<table>"
            "<tr><td>试验项目</td><td>电压等级</td><td>标准值</td><td>备注</td></tr>"
            "<tr><td rowspan=\"2\">电气强度</td><td>750kV</td><td>≥70kV</td><td rowspan=\"2\">平板电极间隙</td></tr>"
            "<tr><td>500kV</td><td>≥60kV</td></tr>"
            "</table>"
        ),
    )

    entries = deterministic_table_entries_from_block(block, strategy="parameter_limit_table")

    assert entries == [
        {
            "clause_no": None,
            "clause_title": "表 4.2.4 变压器内油样性能",
            "clause_text": "电气强度：电压等级750kV，标准值≥70kV；电压等级500kV，标准值≥60kV；备注：平板电极间隙。",
            "summary": None,
            "tags": [],
            "page_start": 18,
            "page_end": 18,
            "clause_type": "normative",
            "source_type": "table",
            "source_ref": "table:t1",
            "source_refs": ["table:t1"],
            "source_label": "表格: 表 4.2.4 变压器内油样性能",
            "table_strategy": "parameter_limit_table",
        }
    ]


def test_form_template_table_is_preserved_but_not_inflated_into_clauses() -> None:
    block = _block(
        title="表 B.0.1 施工检查记录",
        html=(
            "<table>"
            "<tr><td>工程名称</td><td></td><td>施工单位</td><td></td></tr>"
            "<tr><td>检查人</td><td></td><td>日期</td><td></td></tr>"
            "</table>"
        ),
    )

    assert classify_table_strategy(block.table_title, expand_table_rows(block.table_html)) == "form_template_table"
    assert deterministic_table_entries_from_block(block, strategy="form_template_table") == []
