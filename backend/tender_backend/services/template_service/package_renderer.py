from __future__ import annotations

import io
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.shared import Inches
from psycopg import Connection

from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository
from tender_backend.services.template_service.context_preview import build_item_render_context
from tender_backend.services.template_service.docx_renderer import render_template_item_docx
from tender_backend.services.vision_service.pdf_renderer import render_pdf_to_pages


_RENDER_BUNDLE_ROOT = Path("/tmp/tender_template_bundles")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}
_PDF_SUFFIXES = {".pdf"}


def _sanitize_path_segment(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    return cleaned or "bundle"


def _bundle_dir_name(display_name: str, package_key: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = _sanitize_path_segment(display_name or package_key)
    return f"{base}_{stamp}"


def _safe_relative_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe relative path: {relative_path}")
    return path


def _create_zip_archive(bundle_dir: Path) -> Path:
    zip_path = bundle_dir.with_suffix(".zip")
    with ZipFile(zip_path, mode="w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=str(Path(bundle_dir.name) / path.relative_to(bundle_dir)))
    return zip_path


def _collect_evidence_assets(value: object) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    seen: set[str] = set()

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("file_path") and node.get("file_name"):
                key = str(node.get("id") or f"{node.get('file_path')}::{node.get('file_name')}")
                if key not in seen:
                    seen.add(key)
                    collected.append(node)
            for child in node.values():
                _walk(child)
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(value)
    return collected


def _copy_attachment_file(asset: dict[str, object], attachment_dir: Path) -> tuple[Path, str]:
    source_path = Path(str(asset["file_path"])).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(f"attachment file not found: {source_path}")

    file_name = _sanitize_path_segment(str(asset.get("file_name") or source_path.name))
    if "." not in file_name and source_path.suffix:
        file_name = f"{file_name}{source_path.suffix}"
    destination = attachment_dir / file_name
    suffix = 1
    while destination.exists():
        destination = attachment_dir / f"{destination.stem}_{suffix}{destination.suffix}"
        suffix += 1
    shutil.copy2(source_path, destination)
    return destination, source_path.name


def _is_image_asset(source_path: Path, asset: dict[str, object]) -> bool:
    media_type = str(asset.get("media_type") or "").lower()
    return source_path.suffix.lower() in _IMAGE_SUFFIXES or media_type.startswith("image/")


def _is_pdf_asset(source_path: Path, asset: dict[str, object]) -> bool:
    media_type = str(asset.get("media_type") or "").lower()
    return source_path.suffix.lower() in _PDF_SUFFIXES or media_type == "application/pdf"


def _max_inline_width_inches(doc: Document) -> float:
    section = doc.sections[0]
    return max(1.0, float(section.page_width - section.left_margin - section.right_margin) / 914400)


def _embed_asset_preview(doc: Document, *, source_path: Path, asset: dict[str, object]) -> bool:
    width_inches = _max_inline_width_inches(doc)

    if _is_image_asset(source_path, asset):
        doc.add_picture(str(source_path), width=Inches(width_inches))
        return True

    if _is_pdf_asset(source_path, asset):
        pages = render_pdf_to_pages(str(source_path), dpi=150)
        for page in pages:
            doc.add_paragraph(f"第 {page.page_number} 页")
            doc.add_picture(io.BytesIO(page.png_bytes), width=Inches(width_inches))
        return True

    return False


def _render_attachment_manifest(
    *,
    item_name: str,
    output_docx_path: Path,
    attachment_dir: Path,
    assets: list[dict[str, object]],
) -> list[dict[str, object]]:
    attachment_dir.mkdir(parents=True, exist_ok=True)
    copied_assets: list[dict[str, object]] = []
    doc = Document()
    doc.add_heading(item_name, level=1)
    doc.add_paragraph("附件材料清单")

    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    header = table.rows[0].cells
    header[0].text = "材料名称"
    header[1].text = "文件名"
    header[2].text = "归属类型"
    header[3].text = "归属记录"
    header[4].text = "有效期止"
    header[5].text = "导出位置"

    for asset in assets:
        source_path = Path(str(asset["file_path"])).expanduser()
        copied_path, original_name = _copy_attachment_file(asset, attachment_dir)
        relative_export = copied_path.relative_to(output_docx_path.parent)
        preview_embedded = False
        copied_assets.append(
            {
                "asset_id": str(asset.get("id") or ""),
                "asset_name": asset.get("asset_name"),
                "file_name": original_name,
                "output_path": str(copied_path),
                "relative_output_path": str(relative_export),
                "preview_embedded": preview_embedded,
            }
        )
        row = table.add_row().cells
        row[0].text = str(asset.get("asset_name") or "")
        row[1].text = original_name
        row[2].text = str(asset.get("owner_type") or "")
        row[3].text = str(asset.get("owner_id") or "")
        row[4].text = str(asset.get("expires_on") or "")
        row[5].text = str(relative_export)

        doc.add_page_break()
        doc.add_heading(str(asset.get("asset_name") or original_name), level=2)
        doc.add_paragraph(f"源文件: {original_name}")
        doc.add_paragraph(f"导出位置: {relative_export}")
        preview_embedded = _embed_asset_preview(doc, source_path=source_path, asset=asset)
        if not preview_embedded:
            doc.add_paragraph("该文件类型暂不支持直接嵌入预览，请打开同级附件文件。")
        copied_assets[-1]["preview_embedded"] = preview_embedded

    output_docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_docx_path))
    return copied_assets


def _render_attachment_item(
    conn: Connection,
    *,
    item,
    bundle_dir: Path,
) -> dict[str, object]:
    render_context = build_item_render_context(conn, item_id=item.id)
    if not render_context["ready"]:
        missing = ", ".join(render_context["missing_required_bindings"])
        raise ValueError(f"template item is not ready for rendering: missing {missing}")

    assets = _collect_evidence_assets(render_context["context"])
    if not assets:
        raise ValueError("attachment item has no evidence assets to export")

    relative_path = _safe_relative_path(item.relative_path)
    output_docx_path = bundle_dir / relative_path
    attachment_dir = output_docx_path.parent / f"{output_docx_path.stem}_attachments"
    copied_assets = _render_attachment_manifest(
        item_name=item.item_name,
        output_docx_path=output_docx_path,
        attachment_dir=attachment_dir,
        assets=assets,
    )
    return {
        "output_path": str(output_docx_path),
        "copied_assets": copied_assets,
        "copied_asset_count": len(copied_assets),
        "embedded_preview_count": sum(1 for asset in copied_assets if asset.get("preview_embedded")),
        "context_keys": sorted(render_context["context"].keys()),
    }


def render_template_package_bundle(
    conn: Connection,
    *,
    package_id: UUID,
    include_zip: bool = False,
    output_root: Path | None = None,
) -> dict[str, object]:
    repo = BidTemplatePackageRepository()
    package = repo.get_by_id(conn, package_id=package_id)
    if package is None:
        raise LookupError("template package not found")

    items = repo.list_items(conn, package_id=package_id)
    bundle_root = output_root or _RENDER_BUNDLE_ROOT
    bundle_dir = bundle_root / _bundle_dir_name(package.display_name, package.package_key)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    item_results: list[dict[str, object]] = []
    rendered_count = 0
    failed_count = 0

    for item in items:
        try:
            relative_path = _safe_relative_path(item.relative_path)
            if item.render_mode == "attachment" or item.item_type == "evidence":
                rendered = _render_attachment_item(conn, item=item, bundle_dir=bundle_dir)
            else:
                item_output_dir = bundle_dir / relative_path.parent
                rendered = render_template_item_docx(
                    conn,
                    item_id=item.id,
                    output_dir=item_output_dir,
                    output_filename=relative_path.name,
                )
            item_results.append(
                {
                    "item_id": str(item.id),
                    "item_name": item.item_name,
                    "filename": item.filename,
                    "relative_path": item.relative_path,
                    "render_mode": item.render_mode,
                    "status": "rendered",
                    "output_path": rendered["output_path"],
                    "copied_asset_count": rendered.get("copied_asset_count", 0),
                    "embedded_preview_count": rendered.get("embedded_preview_count", 0),
                }
            )
            rendered_count += 1
        except Exception as exc:
            item_results.append(
                {
                    "item_id": str(item.id),
                    "item_name": item.item_name,
                    "filename": item.filename,
                    "relative_path": item.relative_path,
                    "render_mode": item.render_mode,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            failed_count += 1

    zip_path = str(_create_zip_archive(bundle_dir)) if include_zip else None
    return {
        "package_id": str(package.id),
        "package_key": package.package_key,
        "display_name": package.display_name,
        "package_type": package.package_type,
        "output_dir": str(bundle_dir),
        "total_item_count": len(items),
        "rendered_count": rendered_count,
        "failed_count": failed_count,
        "zip_path": zip_path,
        "items": item_results,
    }
