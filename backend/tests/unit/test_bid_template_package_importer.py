from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

import pytest

from tender_backend.core.config import get_settings
from tender_backend.db.repositories.bid_template_package_repo import BidTemplateItemCreate
from tender_backend.services.template_service.package_importer import (
    SingleDocxTemplateSource,
    build_template_items_from_directory,
    _default_package_key,
    infer_package_type,
    import_template_package_from_directory,
)


def test_infer_package_type_from_chinese_folder_name() -> None:
    assert infer_package_type("20258B商务文件") == "business"
    assert infer_package_type("20258B-9013006-0301包1技术文件") == "technical"
    assert infer_package_type("其他资料") == "unknown"


def test_default_package_key_for_chinese_docx_uses_stable_hash() -> None:
    key = _default_package_key(Path("商务标完整模板.docx"), "business")

    assert key.startswith("template-package-")
    assert key.endswith("-business")
    assert key == _default_package_key(Path("商务标完整模板.docx"), "business")


def test_build_template_items_from_directory_infers_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    import_root = tmp_path / "imports"
    import_root.mkdir()
    nested = import_root / "20258B商务文件"
    nested.mkdir()
    template_path = nested / "20258B商务文件.docx"
    template_path.write_bytes(b"docx")

    monkeypatch.setenv("TEMPLATE_IMPORT_ROOTS", str(import_root))
    get_settings.cache_clear()
    items = build_template_items_from_directory(nested)

    assert len(items) == 1
    assert items[0].item_code is None
    assert items[0].item_name == "20258B商务文件"
    assert items[0].filename == "20258B商务文件.docx"
    assert items[0].relative_path == "20258B商务文件.docx"
    assert items[0].item_type == "document"
    assert items[0].render_mode == "single_docx"


def test_build_template_items_from_directory_rejects_multiple_docx_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    import_root = tmp_path / "imports"
    source_dir = import_root / "20258B商务文件"
    source_dir.mkdir(parents=True)
    (source_dir / "商务标完整模板.docx").write_bytes(b"docx")
    (source_dir / "资格审查完整模板.docx").write_bytes(b"docx")

    monkeypatch.setenv("TEMPLATE_IMPORT_ROOTS", str(import_root))
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="Single-DOCX template packages are required"):
        build_template_items_from_directory(source_dir)


def test_build_template_items_from_docx_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    import_root = tmp_path / "imports"
    import_root.mkdir()
    template_path = import_root / "商务标完整模板.docx"
    template_path.write_bytes(b"docx")

    monkeypatch.setenv("TEMPLATE_IMPORT_ROOTS", str(import_root))
    get_settings.cache_clear()

    items = build_template_items_from_directory(template_path)

    assert len(items) == 1
    assert items[0].filename == "商务标完整模板.docx"
    assert items[0].relative_path == "商务标完整模板.docx"
    assert items[0].render_mode == "single_docx"


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
        "tender_backend.services.template_service.package_importer._resolve_single_docx_template_source",
        lambda source_dir: SingleDocxTemplateSource(root_dir=root_dir, docx_path=root_dir / "20258B商务文件.docx"),
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
