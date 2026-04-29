from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from tender_backend.db.repositories.bid_template_package_repo import BidTemplateItemRow, BidTemplatePackageRow
from tender_backend.services.template_service.package_renderer import (
    _bundle_dir_name,
    render_template_package_bundle,
)


def test_bundle_dir_name_preserves_readable_unicode_and_removes_path_separators() -> None:
    name = _bundle_dir_name("20258B/商务文件", "pkg-key")
    assert "20258B_商务文件" in name
    assert "/" not in name


def test_render_template_package_bundle_writes_relative_files_and_zip(
    monkeypatch,
    tmp_path: Path,
) -> None:
    package_id = uuid4()
    item_id = uuid4()
    package = BidTemplatePackageRow(
        id=package_id,
        package_key="pkg-key",
        display_name="20258B商务文件",
        package_type="business",
        source_root="/tmp/source",
        source_manifest={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    item = BidTemplateItemRow(
        id=item_id,
        package_id=package_id,
        item_code="5.1",
        item_name="基本情况表",
        filename="5.1.基本情况表.docx",
        relative_path="sections/5.1.基本情况表.docx",
        source_kind="docx",
        item_type="table",
        render_mode="templated",
        is_required=True,
        sort_order=1,
        created_at=datetime.now(),
    )

    class _Repo:
        def get_by_id(self, conn, *, package_id):
            return package

        def list_items(self, conn, *, package_id):
            return [item]

    def _fake_render(conn, *, item_id, output_dir, output_filename):
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / output_filename
        output_path.write_bytes(b"docx")
        return {"output_path": str(output_path)}

    monkeypatch.setattr(
        "tender_backend.services.template_service.package_renderer.BidTemplatePackageRepository",
        lambda: _Repo(),
    )
    monkeypatch.setattr(
        "tender_backend.services.template_service.package_renderer.render_template_item_docx",
        _fake_render,
    )

    result = render_template_package_bundle(None, package_id=package_id, include_zip=True, output_root=tmp_path)

    bundle_dir = Path(result["output_dir"])
    assert result["rendered_count"] == 1
    assert result["failed_count"] == 0
    assert (bundle_dir / "sections" / "5.1.基本情况表.docx").exists()
    assert result["zip_path"] is not None
    assert Path(result["zip_path"]).exists()
