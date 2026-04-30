from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from tender_backend.core.config import get_settings
from tender_backend.core.path_safety import ensure_path_within_roots, parse_root_list
from tender_backend.db.repositories.bid_template_package_repo import (
    BidTemplateItemCreate,
    BidTemplatePackageRepository,
)


_CODED_NAME_RE = re.compile(r"^(?P<code>\d+(?:\.\d+)*)\.(?P<title>.+)$")
_KEY_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_OPTIONAL_MARKERS = ("如有", "若", "适用于", "联合体", "无需递交")
_EVIDENCE_MARKERS = (
    "证明材料",
    "证书",
    "报告",
    "执照",
    "许可证",
    "截图",
    "凭证",
    "合同",
    "发票",
    "保函",
)


@dataclass(frozen=True)
class ImportedTemplatePackage:
    package_id: str
    package_key: str
    display_name: str
    package_type: str
    source_root: str
    item_count: int


@dataclass(frozen=True)
class SingleDocxTemplateSource:
    root_dir: Path
    docx_path: Path


def infer_package_type(name: str) -> str:
    if "技术" in name:
        return "technical"
    if "商务" in name:
        return "business"
    return "unknown"


def infer_item_type(item_name: str) -> str:
    if any(marker in item_name for marker in _EVIDENCE_MARKERS):
        return "evidence"
    if "表" in item_name:
        return "table"
    return "chapter"


def infer_render_mode(item_type: str) -> str:
    if item_type == "evidence":
        return "attachment"
    return "templated"


def infer_required(item_name: str) -> bool:
    return not any(marker in item_name for marker in _OPTIONAL_MARKERS)


def _default_package_key(root: Path, package_type: str) -> str:
    name = root.stem if root.suffix.lower() == ".docx" else root.name
    tokens = _KEY_TOKEN_RE.findall(name)
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    prefix = "-".join(token.lower() for token in tokens[:3]) if tokens else f"template-package-{digest}"
    return f"{prefix}-{package_type}"


def _parse_item_name(stem: str) -> tuple[str | None, str]:
    match = _CODED_NAME_RE.match(stem)
    if not match:
        return None, stem
    return match.group("code"), match.group("title")


def _sort_key(path: Path) -> tuple[tuple[int, ...], str]:
    code, title = _parse_item_name(path.stem)
    if code:
        return tuple(int(part) for part in code.split(".")), title
    return (10**9,), path.stem


def _resolve_single_docx_template_source(source_path: str | Path) -> SingleDocxTemplateSource:
    settings = get_settings()
    allowed_roots = parse_root_list(settings.template_import_roots)
    if not allowed_roots:
        raise ValueError("template import roots are not configured")

    resolved = ensure_path_within_roots(source_path, allowed_roots, label="template source path")
    if not resolved.exists():
        raise FileNotFoundError(f"Template source path not found: {resolved}")

    if resolved.is_file():
        if resolved.suffix.lower() != ".docx":
            raise ValueError(f"Template source file must be a DOCX file: {resolved}")
        return SingleDocxTemplateSource(root_dir=resolved.parent, docx_path=resolved)

    if not resolved.is_dir():
        raise NotADirectoryError(f"Template source path is not a file or directory: {resolved}")

    files = sorted(
        [
            path for path in resolved.rglob("*")
            if path.is_file() and path.suffix.lower() == ".docx"
        ],
        key=_sort_key,
    )
    if not files:
        raise ValueError(f"No DOCX template file found in: {resolved}")
    if len(files) > 1:
        raise ValueError(
            "Single-DOCX template packages are required; "
            f"found {len(files)} DOCX files in: {resolved}"
        )
    return SingleDocxTemplateSource(root_dir=resolved, docx_path=files[0])


def build_template_items_from_directory(source_dir: str | Path) -> list[BidTemplateItemCreate]:
    source = _resolve_single_docx_template_source(source_dir)
    item_code, item_name = _parse_item_name(source.docx_path.stem)
    return [
        BidTemplateItemCreate(
            item_code=item_code,
            item_name=item_name,
            filename=source.docx_path.name,
            relative_path=str(source.docx_path.relative_to(source.root_dir)),
            source_kind="docx",
            item_type="document",
            render_mode="single_docx",
            is_required=infer_required(item_name),
            sort_order=0,
        )
    ]


def import_template_package_from_directory(
    conn,
    *,
    source_dir: str | Path,
    package_key: str | None = None,
    display_name: str | None = None,
    package_type: str | None = None,
    category_code: str | None = None,
) -> ImportedTemplatePackage:
    source = _resolve_single_docx_template_source(source_dir)
    items = build_template_items_from_directory(source_dir)
    root_dir = source.root_dir

    resolved_display_name = (display_name or source.docx_path.stem).strip()
    resolved_package_type = (package_type or infer_package_type(resolved_display_name)).strip() or "unknown"
    resolved_package_key = (package_key or _default_package_key(source.docx_path, resolved_package_type)).strip()

    repo = BidTemplatePackageRepository()
    with conn.transaction():
        package = repo.upsert_package(
            conn,
            package_key=resolved_package_key,
            display_name=resolved_display_name,
            package_type=resolved_package_type,
            category_code=(category_code or "").strip() or None,
            source_root=str(root_dir),
            source_manifest={
                "file_count": 1,
                "import_mode": "single_docx",
                "source_dir_name": root_dir.name,
                "template_file": source.docx_path.name,
                "relative_paths": [item.relative_path for item in items],
            },
        )
        repo.replace_items(conn, package_id=package.id, items=items)
    return ImportedTemplatePackage(
        package_id=str(package.id),
        package_key=package.package_key,
        display_name=package.display_name,
        package_type=package.package_type,
        source_root=package.source_root,
        item_count=len(items),
    )
