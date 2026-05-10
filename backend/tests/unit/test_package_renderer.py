from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import fitz  # PyMuPDF
import pytest
from docx import Document

from tender_backend.core.config import get_settings
from tender_backend.db.repositories.bid_template_package_repo import BidTemplateItemRow, BidTemplatePackageRow
from tender_backend.services.template_service.package_renderer import (
    _attachment_display_title,
    _attachment_template_kind,
    _bundle_dir_name,
    _collect_evidence_assets,
    preflight_template_package_bundle,
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
        category_code=None,
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
    assert result["required_failed_count"] == 0
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


def test_attachment_display_title_uses_chinese_subsection_number() -> None:
    assert _attachment_display_title("能源管理体系认证证书", "12.1") == "（一）能源管理体系认证证书"
    assert _attachment_display_title("投标保证金缴纳证明材料", "23.2") == "（二）投标保证金缴纳证明材料"
    assert _attachment_display_title("企业营业执照", "3") == "企业营业执照"


def test_attachment_template_kind_classifies_common_evidence_types() -> None:
    assert _attachment_template_kind("企业营业执照（或事业单位法人证书）", []) == "license"
    assert _attachment_template_kind("能源管理体系认证证书", []) == "certificate"
    assert _attachment_template_kind("法定代表人授权委托书", []) == "authorization"
    assert _attachment_template_kind("投标保证金缴纳证明材料（汇款底单或保函）", []) == "contract"


def test_render_attachment_manifest_embeds_image_and_pdf_previews(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    monkeypatch.setenv("EVIDENCE_UPLOAD_DIR", str(upload_root))
    get_settings.cache_clear()
    image_path = tmp_path / "license.png"
    image_path.write_bytes(_PNG_1X1)

    pdf_path = tmp_path / "certificate.pdf"
    pdf = fitz.open()
    for page_no in range(2):
        page = pdf.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Page {page_no + 1}", fontsize=24)
    pdf.save(pdf_path)
    pdf.close()

    managed_image_path = upload_root / image_path.name
    managed_image_path.write_bytes(image_path.read_bytes())
    managed_pdf_path = upload_root / pdf_path.name
    managed_pdf_path.write_bytes(pdf_path.read_bytes())

    output_docx_path = tmp_path / "7.1.资质证书证明材料.docx"
    attachment_dir = tmp_path / "7.1.资质证书证明材料_attachments"
    copied_assets = _render_attachment_manifest(
        item_name="资质证书证明材料",
        item_code="7.1",
        output_docx_path=output_docx_path,
        attachment_dir=attachment_dir,
        assets=[
            {
                "id": "img-1",
                "asset_name": "营业执照",
                "file_name": managed_image_path.name,
                "file_path": str(managed_image_path),
                "media_type": "image/png",
                "owner_type": "company_profile",
            },
            {
                "id": "pdf-1",
                "asset_name": "质量认证证书",
                "file_name": managed_pdf_path.name,
                "file_path": str(managed_pdf_path),
                "media_type": "application/pdf",
                "owner_type": "qualification_certificate",
            },
        ],
    )

    saved = Document(str(output_docx_path))
    assert len(saved.inline_shapes) == 3
    assert saved.paragraphs[0].text == "（一）资质证书证明材料"
    assert copied_assets[0]["preview_embedded"] is True
    assert copied_assets[1]["preview_embedded"] is True
    assert (attachment_dir / managed_image_path.name).exists()
    assert (attachment_dir / managed_pdf_path.name).exists()


def test_render_attachment_manifest_rejects_assets_outside_upload_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    monkeypatch.setenv("EVIDENCE_UPLOAD_DIR", str(upload_root))
    get_settings.cache_clear()

    external_file = tmp_path / "external.pdf"
    external_file.write_bytes(b"%PDF-1.7\n")

    with pytest.raises(FileNotFoundError, match="must be within"):
        _render_attachment_manifest(
            item_name="资质证书证明材料",
            item_code="7.1",
            output_docx_path=tmp_path / "out.docx",
            attachment_dir=tmp_path / "attachments",
            assets=[
                {
                    "id": "pdf-1",
                    "asset_name": "质量认证证书",
                    "file_name": external_file.name,
                    "file_path": str(external_file),
                    "media_type": "application/pdf",
                    "owner_type": "qualification_certificate",
                }
            ],
        )


def test_preflight_template_package_bundle_reports_attachment_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    package_id = uuid4()
    item_id = uuid4()
    package = BidTemplatePackageRow(
        id=package_id,
        package_key="pkg-key",
        display_name="资质文件包",
        package_type="business",
        category_code=None,
        source_root="/tmp/source",
        source_manifest={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    item = BidTemplateItemRow(
        id=item_id,
        package_id=package_id,
        item_code="7.1",
        item_name="资质证书证明材料",
        filename="7.1.资质证书证明材料.docx",
        relative_path="sections/7.1.资质证书证明材料.docx",
        source_kind="docx",
        item_type="evidence",
        render_mode="attachment",
        is_required=True,
        sort_order=1,
        created_at=datetime.now(),
    )

    class _Repo:
        def get_by_id(self, conn, *, package_id):
            return package

        def list_items(self, conn, *, package_id):
            return [item]

    monkeypatch.setattr(
        "tender_backend.services.template_service.package_renderer.BidTemplatePackageRepository",
        lambda: _Repo(),
    )
    monkeypatch.setattr(
        "tender_backend.services.template_service.package_renderer.build_item_render_context",
        lambda conn, *, item_id: {
            "ready": True,
            "missing_required_bindings": [],
            "context": {
                "assets": [
                    {
                        "id": "asset-1",
                        "asset_name": "缺失证书",
                        "file_name": "missing.pdf",
                        "file_path": "/tmp/missing.pdf",
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        "tender_backend.services.template_service.package_renderer._validated_asset_source_path",
        lambda asset: (_ for _ in ()).throw(FileNotFoundError("attachment file not found: /tmp/missing.pdf")),
    )

    result = preflight_template_package_bundle(None, package_id=package_id)

    assert result["ready"] is False
    assert result["ready_item_count"] == 0
    assert result["blocked_item_count"] == 1
    assert result["issue_count"] == 1
    assert result["items"][0]["asset_count"] == 1
    assert result["items"][0]["invalid_asset_count"] == 1
    assert result["items"][0]["issues"][0]["code"] == "invalid_evidence_asset"


def test_render_template_package_bundle_counts_required_failures(monkeypatch, tmp_path: Path) -> None:
    package_id = uuid4()
    item = BidTemplateItemRow(
        id=uuid4(),
        package_id=package_id,
        item_code="7.1",
        item_name="资质证书证明材料",
        filename="7.1.资质证书证明材料.docx",
        relative_path="sections/7.1.资质证书证明材料.docx",
        source_kind="docx",
        item_type="table",
        render_mode="templated",
        is_required=True,
        sort_order=1,
        created_at=datetime.now(),
    )
    package = BidTemplatePackageRow(
        id=package_id,
        package_key="pkg-key",
        display_name="商务文件",
        package_type="business",
        category_code=None,
        source_root="/tmp/source",
        source_manifest={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    class _Repo:
        def get_by_id(self, conn, *, package_id):
            return package

        def list_items(self, conn, *, package_id):
            return [item]

    monkeypatch.setattr("tender_backend.services.template_service.package_renderer.BidTemplatePackageRepository", lambda: _Repo())
    monkeypatch.setattr(
        "tender_backend.services.template_service.package_renderer.render_template_item_docx",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("render failed")),
    )

    result = render_template_package_bundle(None, package_id=package_id, output_root=tmp_path)

    assert result["failed_count"] == 1
    assert result["required_failed_count"] == 1
    assert result["items"][0]["required"] is True
