from __future__ import annotations

from tender_backend.services.export_service.personnel_table_renderer import PersonnelTableRenderer


def test_personnel_table_renderer_formats_snapshot_row() -> None:
    renderer = PersonnelTableRenderer()
    row = renderer._row_to_preview_row(
        1,
        {
            "full_name": "张三",
            "intended_role": "项目负责人",
            "gender": "男",
            "age": 36,
            "education": "本科",
            "title": "高级工程师",
            "specialty": "电力工程",
            "years_experience": 12,
            "phone": "13800000000",
            "attachments": [
                {
                    "asset_category": "practice_certificate",
                    "expires_on": "2028-12-31",
                    "metadata_json": {"cert_no": "渝123"},
                }
            ],
        },
    )

    assert row["序号"] == "1"
    assert row["姓名"] == "张三"
    assert row["拟任岗位"] == "项目负责人"
    assert row["从业年限"] == "12年"
    assert row["联系方式"] == "13800000000"
    assert row["主要证件/附件"] == "执业资格证(渝123) 有效期至2028-12-31"
