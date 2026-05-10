"""Build final bid delivery ZIP packages."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.services.export_service.doc_converter import convert_docx_to_doc
from tender_backend.services.export_service.docx_exporter import EXPORT_ROOT, render_docx, render_volume_docx
from tender_backend.services.export_service.equipment_table_renderer import EquipmentTableRenderer
from tender_backend.services.compliance_check_service import ComplianceCheckService
from tender_backend.services.review_service.compliance_matrix import build_compliance_matrix
from tender_backend.services.review_service.review_engine import build_project_review
from tender_backend.services.submission_checklist_service import SubmissionChecklistService
from tender_backend.services.tender_constraint_service import TenderConstraintService

__all__ = [
    "build_delivery_package",
    "convert_docx_to_doc",
    "get_delivery_package",
    "list_delivery_packages",
]


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    return path


def _next_version(conn: Connection, project_id: UUID) -> int:
    with conn.cursor() as cur:
        row = cur.execute(
            "SELECT COALESCE(MAX(version_no), 0) + 1 FROM bid_delivery_package WHERE project_id = %s",
            (project_id,),
        ).fetchone()
    return int(row[0] if row else 1)


def _project_name(conn: Connection, project_id: UUID) -> str:
    with conn.cursor() as cur:
        row = cur.execute("SELECT name FROM project WHERE id = %s", (project_id,)).fetchone()
    return str(row[0]) if row and row[0] else str(project_id)


def _load_confirmation_records(conn: Connection, project_id: UUID) -> list[dict]:
    constraint_set = TenderConstraintService().latest_confirmed(conn, project_id=project_id)
    if constraint_set:
        return [
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "constraint_subtype": item.get("constraint_subtype") or (item.get("metadata_json") or {}).get("constraint_subtype"),
                "title": item.get("title"),
                "human_confirmed": item.get("status") in {"accepted", "confirmed"},
                "confirmed_by": (item.get("metadata_json") or {}).get("confirmed_by"),
                "confirmed_at": item.get("updated_at") or item.get("created_at"),
                "review_status": item.get("status"),
                "source_constraint_set_id": constraint_set.get("id"),
            }
            for item in constraint_set.get("items") or []
        ]
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT id, category, title, human_confirmed, confirmed_by, confirmed_at, review_status
            FROM project_requirement
            WHERE project_id = %s
              AND COALESCE(is_stale, false) = false
            ORDER BY category, created_at
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _load_traceability(conn: Connection, project_id: UUID) -> list[dict]:
    constraint_set = TenderConstraintService().latest_confirmed(conn, project_id=project_id)
    if constraint_set:
        return [
            {
                "id": item.get("id"),
                "requirement_id": item.get("requirement_id"),
                "category": item.get("category"),
                "constraint_subtype": item.get("constraint_subtype") or (item.get("metadata_json") or {}).get("constraint_subtype"),
                "title": item.get("title"),
                "source_file": item.get("source_file"),
                "source_locator": item.get("source_locator"),
                "chapter_code": (item.get("metadata_json") or {}).get("mapped_chapter_code"),
                "chapter_title": (item.get("metadata_json") or {}).get("mapped_chapter_title"),
                "source_constraint_set_id": constraint_set.get("id"),
            }
            for item in constraint_set.get("items") or []
        ]
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT pr.id, pr.category, pr.title, pr.source_file, pr.source_locator,
                   bc.chapter_code, bc.chapter_title
            FROM project_requirement pr
            LEFT JOIN bid_chapter_requirement bcr ON bcr.requirement_id = pr.id
            LEFT JOIN bid_chapter bc ON bc.id = bcr.bid_chapter_id
            WHERE pr.project_id = %s
              AND COALESCE(pr.is_stale, false) = false
            ORDER BY pr.category, pr.created_at
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _load_missing_items(conn: Connection, project_id: UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT rm.*, pr.category, pr.title AS requirement_title
            FROM requirement_match rm
            JOIN project_requirement pr ON pr.id = rm.requirement_id
            WHERE pr.project_id = %s
              AND rm.match_status IN ('missing', 'needs_review')
            ORDER BY pr.category, pr.created_at
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def build_delivery_package(conn: Connection, *, project_id: UUID, created_by: str | None = None) -> dict[str, Any]:
    blocking_compliance = ComplianceCheckService().blocking_findings(conn, project_id=project_id)
    if blocking_compliance:
        raise ValueError(f"unresolved P0 compliance findings block delivery package: {len(blocking_compliance)}")

    version = _next_version(conn, project_id)
    project_name = _project_name(conn, project_id)
    root = EXPORT_ROOT / str(project_id) / f"delivery-v{version}"
    root.mkdir(parents=True, exist_ok=True)

    docx_path = render_docx(conn, project_id=project_id, output_path=root / "投标文件.docx")
    doc_path = convert_docx_to_doc(docx_path)
    equipment_xlsx_path = root / "主要施工设备一览表.xlsx"
    equipment_xlsx_path.write_bytes(EquipmentTableRenderer().render_attachment_xlsx(conn, project_id=project_id))
    warnings: list[dict[str, str]] = []
    if doc_path is None:
        warnings.append({"code": "doc_conversion_unavailable", "message": "DOC conversion did not produce an output file"})
    volume_paths: list[Path] = []
    for volume in ("qualification", "business", "technical"):
        try:
            volume_paths.append(render_volume_docx(conn, project_id=project_id, volume_type=volume, output_path=root / f"{volume}.docx"))
        except Exception as exc:
            warnings.append({"code": "volume_render_failed", "volume": volume, "message": str(exc)})

    review_issues = build_project_review(conn, project_id=project_id)
    review_report_path = _write_json(root / "审查报告.json", {"issues": [issue.__dict__ for issue in review_issues]})
    matrix_entries = build_compliance_matrix(conn, project_id=project_id)
    response_matrix_path = _write_json(root / "约束响应矩阵.json", {"entries": [entry.__dict__ for entry in matrix_entries]})
    missing_items_path = _write_json(root / "资料缺失清单.json", {"items": _load_missing_items(conn, project_id)})
    traceability_path = _write_json(root / "来源追溯清单.json", {"items": _load_traceability(conn, project_id)})
    confirmation_record_path = _write_json(root / "人工确认记录.json", {"items": _load_confirmation_records(conn, project_id)})
    submission_checklist_path = _write_json(
        root / "递交准备清单.json",
        SubmissionChecklistService().build(conn, project_id=project_id),
    )

    package_name = f"{project_name}-投标交付包-v{version}.zip"
    package_path = root.parent / package_name
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [docx_path, *([doc_path] if doc_path else []), equipment_xlsx_path, *volume_paths, review_report_path, response_matrix_path, missing_items_path, traceability_path, confirmation_record_path, submission_checklist_path]:
            archive.write(path, path.name)

    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            INSERT INTO bid_delivery_package (
              id, project_id, version_no, status, package_name, package_path,
              docx_path, doc_path, review_report_path, response_matrix_path, missing_items_path,
              traceability_path, confirmation_record_path, metadata_json, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                uuid4(),
                project_id,
                version,
                "degraded" if warnings else "created",
                package_name,
                str(package_path),
                str(docx_path),
                str(doc_path) if doc_path else None,
                str(review_report_path),
                str(response_matrix_path),
                str(missing_items_path),
                str(traceability_path),
                str(confirmation_record_path),
                Jsonb({
                    "volume_paths": [str(path) for path in volume_paths],
                    "warnings": warnings,
                    "submission_checklist_path": str(submission_checklist_path),
                    "equipment_table_xlsx_path": str(equipment_xlsx_path),
                }),
                created_by,
            ),
        ).fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("failed to create delivery package record")
    return dict(row)


def get_delivery_package(conn: Connection, *, package_id: UUID) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT * FROM bid_delivery_package WHERE id = %s", (package_id,)).fetchone()
    return dict(row) if row else None


def list_delivery_packages(conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM bid_delivery_package WHERE project_id = %s ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]
