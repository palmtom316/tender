from __future__ import annotations

from pathlib import Path

import pytest

from tender_backend.services.template_service.package_importer import (
    build_template_items_from_directory,
    infer_package_type,
)


def test_infer_package_type_from_chinese_folder_name() -> None:
    assert infer_package_type("20258B商务文件") == "business"
    assert infer_package_type("20258B-9013006-0301包1技术文件") == "technical"
    assert infer_package_type("其他资料") == "unknown"


def test_build_template_items_from_directory_infers_metadata(tmp_path: Path) -> None:
    (tmp_path / "1.商务偏差表.docx").write_bytes(b"docx")
    (tmp_path / "5.1.基本情况表.docx").write_bytes(b"docx")
    (tmp_path / "23.2.投标保证金缴纳证明材料（汇款底单或保单或保函的彩色扫描件）.docx").write_bytes(b"docx")
    (tmp_path / "24.认为需要加以说明的其它商务内容（如有）.docx").write_bytes(b"docx")

    items = build_template_items_from_directory(tmp_path)

    assert [item.item_code for item in items] == ["1", "5.1", "23.2", "24"]
    assert items[0].item_name == "商务偏差表"
    assert items[1].item_type == "table"
    assert items[2].item_type == "evidence"
    assert items[2].render_mode == "attachment"
    assert items[3].is_required is False


def test_build_template_items_from_directory_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_template_items_from_directory(tmp_path)
