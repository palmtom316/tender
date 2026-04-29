from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from psycopg import Connection

from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository
from tender_backend.services.template_service.docx_renderer import render_template_item_docx


_RENDER_BUNDLE_ROOT = Path("/tmp/tender_template_bundles")


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
