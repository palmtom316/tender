from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import fitz  # PyMuPDF
from docx import Document

from tender_backend.db.repositories.bid_template_package_repo import BidTemplateItemRow, BidTemplatePackageRow
from tender_backend.services.template_service.package_renderer import (
    _bundle_dir_name,
    _collect_evidence_assets,
    _render_attachment_manifest,
    render_template_package_bundle,
)


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9p2unMcAAAAASUVORK5CYII="
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


def test_collect_evidence_assets_finds_nested_asset_rows() -> None:
    assets = _collect_evidence_assets(
        {
            "certificate": {
                "certificate_name": "质量管理体系认证证书",
                "attachments": [
                    {
                        "id": "asset-1",
                        "asset_name": "认证证书扫描件",
                        "file_name": "iso.pdf",
                        "file_path": "/tmp/iso.pdf",
                    }
                ],
            }
        }
    )

    assert len(assets) == 1
    assert assets[0]["asset_name"] == "认证证书扫描件"


def test_render_attachment_manifest_embeds_image_and_pdf_previews(tmp_path: Path) -> None:
    image_path = tmp_path / "license.png"
    image_path.write_bytes(_PNG_1X1)

    pdf_path = tmp_path / "certificate.pdf"
    pdf = fitz.open()
    for page_no in range(2):
        page = pdf.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Page {page_no + 1}", fontsize=24)
    pdf.save(pdf_path)
    pdf.close()

    output_docx_path = tmp_path / "7.1.资质证书证明材料.docx"
    attachment_dir = tmp_path / "7.1.资质证书证明材料_attachments"
    copied_assets = _render_attachment_manifest(
        item_name="资质证书证明材料",
        output_docx_path=output_docx_path,
        attachment_dir=attachment_dir,
        assets=[
            {
                "id": "img-1",
                "asset_name": "营业执照",
                "file_name": image_path.name,
                "file_path": str(image_path),
                "media_type": "image/png",
                "owner_type": "company_profile",
            },
            {
                "id": "pdf-1",
                "asset_name": "质量认证证书",
                "file_name": pdf_path.name,
                "file_path": str(pdf_path),
                "media_type": "application/pdf",
                "owner_type": "qualification_certificate",
            },
        ],
    )

    saved = Document(str(output_docx_path))
    assert len(saved.inline_shapes) == 3
    assert copied_assets[0]["preview_embedded"] is True
    assert copied_assets[1]["preview_embedded"] is True
    assert (attachment_dir / image_path.name).exists()
    assert (attachment_dir / pdf_path.name).exists()
