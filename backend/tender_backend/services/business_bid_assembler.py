"""Deterministic qualification-business bid assembly service."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.core.config import get_settings
from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository, BidTemplateItemRow
from tender_backend.services.bid_outline_templates import SGCC_DISTRIBUTION_BUSINESS_TEMPLATE_KEY
from tender_backend.services.template_service.docx_renderer import render_template_item_docx
from tender_backend.services.tender_constraint_service import TenderConstraintService

BUSINESS_VOLUMES = {"qualification", "business"}
BUSINESS_CONSTRAINT_CATEGORIES = {"qualification", "performance", "project_team", "personnel", "business"}
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class BusinessBidAssembler:
    def assemble(self, conn: Connection, *, project_id: UUID, created_by: str | None = None) -> dict[str, Any]:
        outline = self._confirmed_outline(conn, project_id=project_id)
        if outline is None:
            raise ValueError("confirmed outline is required before qualification-business assembly")
        chapters = [row for row in self._outline_chapters(conn, outline_id=outline["id"]) if row["volume_type"] in BUSINESS_VOLUMES]
        constraint_set = TenderConstraintService().latest_confirmed(conn, project_id=project_id)
        missing = self._missing_business_materials(conn, project_id=project_id)
        response_matrix = (
            self._response_matrix_from_constraints(constraint_set)
            if constraint_set
            else self._response_matrix(conn, project_id=project_id, volume_types=BUSINESS_VOLUMES)
        )
        metadata = {
            "chapter_count": len(chapters),
            "missing_material_count": len(missing),
            "constraint_source_of_truth": "confirmed_constraint_set" if constraint_set else "legacy_project_requirement",
        }
        if constraint_set:
            metadata["constraint_set_id"] = str(constraint_set.get("id"))
            metadata["constraint_set_version"] = constraint_set.get("version")
        rendered_artifacts = self._render_docx_artifacts_if_enabled(conn, project_id=project_id, chapters=chapters)
        if rendered_artifacts:
            metadata["rendered_artifact_count"] = len(rendered_artifacts)
        run = self._create_run(
            conn,
            project_id=project_id,
            outline_id=outline["id"],
            volume_type="business",
            strategy="data_insert",
            status="needs_review" if missing else "completed",
            created_by=created_by,
            metadata=metadata,
        )
        return {
            "project_id": str(project_id),
            "run": run,
            "chapters": chapters,
            "rendered_artifacts": rendered_artifacts,
            "response_matrix": response_matrix,
            "missing_materials": missing,
            "boundary": "报价内容不由本服务生成；报价分册仅支持外部附件挂载。",
        }

    def _render_docx_artifacts_if_enabled(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        chapters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        settings = get_settings()
        if not settings.business_bid_docxtpl_enabled:
            return []

        repo = BidTemplatePackageRepository()
        package = repo.get_by_key(conn, package_key=SGCC_DISTRIBUTION_BUSINESS_TEMPLATE_KEY)
        if package is None:
            return []

        items_by_code = {
            item.item_code: item
            for item in repo.list_items(conn, package_id=package.id)
            if item.item_code and item.render_mode == "single_docx_section"
        }
        output_dir = Path(settings.template_render_root) / "business_bid" / str(project_id)
        rendered_artifacts: list[dict[str, Any]] = []
        for chapter in chapters:
            chapter_code = str(chapter.get("chapter_code") or "")
            item = items_by_code.get(chapter_code)
            if item is None:
                continue
            rendered = render_template_item_docx(
                conn,
                item_id=item.id,
                output_dir=output_dir,
                output_filename=_artifact_filename(chapter),
                project_id=project_id,
            )
            artifact_json = _artifact_json(item, rendered=rendered)
            content_md = _artifact_summary(chapter, artifact_json=artifact_json)
            draft = self._upsert_rendered_chapter_draft(
                conn,
                project_id=project_id,
                chapter_code=chapter_code,
                content_md=content_md,
                rendered_docx_path=str(rendered["output_path"]),
                rendered_artifact_json=artifact_json,
            )
            rendered_artifacts.append(
                {
                    "chapter_code": chapter_code,
                    "template_item_id": str(item.id),
                    "rendered_docx_path": draft.get("rendered_docx_path") or str(rendered["output_path"]),
                }
            )
        return rendered_artifacts

    def _upsert_rendered_chapter_draft(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        chapter_code: str,
        content_md: str,
        rendered_docx_path: str,
        rendered_artifact_json: dict[str, Any],
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO chapter_draft (
                  id, project_id, chapter_code, volume_type, content_md,
                  rendered_docx_path, rendered_artifact_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (project_id, volume_type, chapter_code)
                DO UPDATE SET
                  content_md = EXCLUDED.content_md,
                  rendered_docx_path = EXCLUDED.rendered_docx_path,
                  rendered_artifact_json = EXCLUDED.rendered_artifact_json,
                  updated_at = now()
                RETURNING id, chapter_code, rendered_docx_path
                """,
                (
                    uuid4(),
                    project_id,
                    chapter_code,
                    "business",
                    content_md,
                    rendered_docx_path,
                    Jsonb(rendered_artifact_json),
                ),
            ).fetchone()
        return dict(row) if row else {}

    def _confirmed_outline(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT *
                FROM bid_outline
                WHERE project_id = %s AND status = 'confirmed'
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    def _outline_chapters(self, conn: Connection, *, outline_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, chapter_code, chapter_title, volume_type, sort_order, outline_md, metadata_json
                FROM bid_chapter
                WHERE bid_outline_id = %s
                ORDER BY sort_order, chapter_code
                """,
                (outline_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _missing_business_materials(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT rm.*, pr.title AS requirement_title, pr.category
                FROM requirement_match rm
                JOIN project_requirement pr ON pr.id = rm.requirement_id
                WHERE pr.project_id = %s
                  AND pr.category IN ('qualification', 'performance', 'project_team', 'personnel', 'business')
                  AND rm.match_status IN ('missing', 'needs_review')
                ORDER BY pr.category, pr.created_at
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _response_matrix(self, conn: Connection, *, project_id: UUID, volume_types: set[str]) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT pr.id AS requirement_id, pr.category, pr.title AS requirement_title,
                       bc.chapter_code, bc.chapter_title, bcr.priority_level
                FROM bid_chapter_requirement bcr
                JOIN bid_chapter bc ON bc.id = bcr.bid_chapter_id
                JOIN project_requirement pr ON pr.id = bcr.requirement_id
                WHERE pr.project_id = %s AND bc.volume_type = ANY(%s)
                ORDER BY bc.sort_order, pr.category
                """,
                (project_id, list(volume_types)),
            ).fetchall()
        return [dict(row) for row in rows]

    def _response_matrix_from_constraints(self, constraint_set: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in constraint_set.get("items") or []:
            if item.get("category") not in BUSINESS_CONSTRAINT_CATEGORIES:
                continue
            metadata = item.get("metadata_json") or {}
            rows.append(
                {
                    "source_constraint_id": str(item.get("id")),
                    "requirement_id": str(item.get("requirement_id")) if item.get("requirement_id") else None,
                    "category": item.get("category"),
                    "requirement_title": item.get("title"),
                    "constraint_text": item.get("constraint_text"),
                    "source_file": item.get("source_file"),
                    "source_locator": item.get("source_locator"),
                    "constraint_subtype": metadata.get("constraint_subtype") if isinstance(metadata, dict) else None,
                    "priority_level": item.get("confirmation_level") or "normal",
                }
            )
        return rows

    def _create_run(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        outline_id: UUID,
        volume_type: str,
        strategy: str,
        status: str,
        created_by: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO bid_generation_run (
                  id, project_id, bid_outline_id, volume_type, strategy, status, metadata_json, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), project_id, outline_id, volume_type, strategy, status, Jsonb(metadata), created_by),
            ).fetchone()
        conn.commit()
        return dict(row) if row else {}


__all__ = ["BusinessBidAssembler"]


def _artifact_filename(chapter: dict[str, Any]) -> str:
    sort_order = int(chapter.get("sort_order") or 0)
    chapter_code = _UNSAFE_FILENAME_CHARS.sub("_", str(chapter.get("chapter_code") or "chapter")).strip("_")
    return f"{sort_order:03d}-{chapter_code}.docx"


def _artifact_json(item: BidTemplateItemRow, *, rendered: dict[str, object]) -> dict[str, Any]:
    return {
        "template_item_id": str(item.id),
        "render_mode": item.render_mode,
        "missing_materials": [],
        "placeholder_status": {
            "unfilled_count": 0,
            "context_keys": list(rendered.get("context_keys") or []),
        },
    }


def _artifact_summary(chapter: dict[str, Any], *, artifact_json: dict[str, Any]) -> str:
    title = str(chapter.get("chapter_title") or "")
    code = str(chapter.get("chapter_code") or "")
    missing_count = len(artifact_json.get("missing_materials") or [])
    unfilled_count = int((artifact_json.get("placeholder_status") or {}).get("unfilled_count") or 0)
    return "\n".join(
        [
            f"# {code} {title}".strip(),
            "",
            f"- rendered_docx: yes",
            f"- missing_material_count: {missing_count}",
            f"- placeholder_unfilled_count: {unfilled_count}",
        ]
    )
