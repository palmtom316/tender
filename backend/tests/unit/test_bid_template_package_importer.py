from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

import pytest

from tender_backend.core.config import get_settings
from tender_backend.db.repositories.bid_template_package_repo import BidTemplateItemCreate
from tender_backend.services.template_service.package_importer import (
    build_template_items_from_directory,
    infer_package_type,
    import_template_package_from_directory,
)


def test_infer_package_type_from_chinese_folder_name() -> None:
    assert infer_package_type("20258B商务文件") == "business"
    assert infer_package_type("20258B-9013006-0301包1技术文件") == "technical"
    assert infer_package_type("其他资料") == "unknown"


def test_build_template_items_from_directory_infers_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    import_root = tmp_path / "imports"
    import_root.mkdir()
    nested = import_root / "20258B商务文件"
    nested.mkdir()
    (nested / "1.商务偏差表.docx").write_bytes(b"docx")
    (nested / "5.1.基本情况表.docx").write_bytes(b"docx")
    (nested / "23.2.投标保证金缴纳证明材料（汇款底单或保单或保函的彩色扫描件）.docx").write_bytes(b"docx")
    (nested / "24.认为需要加以说明的其它商务内容（如有）.docx").write_bytes(b"docx")

    monkeypatch.setenv("TEMPLATE_IMPORT_ROOTS", str(import_root))
    get_settings.cache_clear()
    items = build_template_items_from_directory(nested)

    assert [item.item_code for item in items] == ["1", "5.1", "23.2", "24"]
    assert items[0].item_name == "商务偏差表"
    assert items[1].item_type == "table"
    assert items[2].item_type == "evidence"
    assert items[2].render_mode == "attachment"
    assert items[3].is_required is False


def test_build_template_items_from_directory_rejects_empty_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("TEMPLATE_IMPORT_ROOTS", str(tmp_path.parent))
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        build_template_items_from_directory(tmp_path)


def test_build_template_items_from_directory_rejects_path_outside_allowed_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("TEMPLATE_IMPORT_ROOTS", str(tmp_path.parent / "allowed"))
    get_settings.cache_clear()
    (tmp_path / "1.商务偏差表.docx").write_bytes(b"docx")
    with pytest.raises(ValueError, match="outside the configured allowed directories"):
        build_template_items_from_directory(tmp_path)


def test_import_template_package_from_directory_uses_single_transaction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    package_id = uuid4()
    root_dir = tmp_path / "imports" / "20258B商务文件"
    items = [
        BidTemplateItemCreate(
            item_code="1",
            item_name="商务偏差表",
            filename="1.商务偏差表.docx",
            relative_path="1.商务偏差表.docx",
            source_kind="docx",
            item_type="table",
            render_mode="templated",
            is_required=True,
            sort_order=0,
        ),
    ]
    calls: list[str] = []

    class _FakeConn:
        @contextmanager
        def transaction(self):
            calls.append("transaction:start")
            try:
                yield
            finally:
                calls.append("transaction:end")

    class _Repo:
        def upsert_package(self, conn, **kwargs):
            calls.append("upsert")
            return SimpleNamespace(
                id=package_id,
                package_key=kwargs["package_key"],
                display_name=kwargs["display_name"],
                package_type=kwargs["package_type"],
                source_root=kwargs["source_root"],
            )

        def replace_items(self, conn, *, package_id: object, items: object):
            calls.append("replace")
            assert package_id == package_id_value
            assert items == expected_items
            return []

    monkeypatch.setattr(
        "tender_backend.services.template_service.package_importer.build_template_items_from_directory",
        lambda source_dir: items,
    )
    monkeypatch.setattr(
        "tender_backend.services.template_service.package_importer.ensure_path_within_roots",
        lambda source_dir, roots, label: root_dir,
    )
    monkeypatch.setattr(
        "tender_backend.services.template_service.package_importer.parse_root_list",
        lambda raw: [tmp_path / "imports"],
    )
    monkeypatch.setattr(
        "tender_backend.services.template_service.package_importer.get_settings",
        lambda: SimpleNamespace(template_import_roots=str(tmp_path / "imports")),
    )
    monkeypatch.setattr(
        "tender_backend.services.template_service.package_importer.BidTemplatePackageRepository",
        lambda: _Repo(),
    )

    package_id_value = package_id
    expected_items = items

    result = import_template_package_from_directory(_FakeConn(), source_dir=root_dir)

    assert result.package_id == str(package_id)
    assert calls == ["transaction:start", "upsert", "replace", "transaction:end"]
