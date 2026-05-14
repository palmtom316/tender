"""Project-scoped template instance creation and maintenance."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from psycopg import Connection

from tender_backend.db.repositories.bid_template_package_repo import (
    BidTemplateItemRow,
    BidTemplatePackageRepository,
    BidTemplatePackageRow,
)
from tender_backend.db.repositories.project_repository import ProjectRepository
from tender_backend.db.repositories.project_template_instance_repo import (
    ProjectTemplateInstanceRepository,
    ProjectTemplateInstanceRow,
)
from tender_backend.db.repositories.requirement_repo import RequirementRepository


_SEAL_RE = re.compile(r"签章|盖章|签字|骑缝章|法定代表人")
_AI_RE = re.compile(r"ai|generate|write|draft|技术|方案|施工|组织|措施", re.IGNORECASE)
_ASSET_RE = re.compile(r"业绩|人员|项目经理|证书|资质|设备|机械|材料")
_PRICING_RE = re.compile(r"报价|清单|工程量|BOQ|price|pricing|excel", re.IGNORECASE)


class ProjectTemplateInstanceService:
    def __init__(
        self,
        *,
        project_repo: ProjectRepository | None = None,
        template_repo: BidTemplatePackageRepository | None = None,
        instance_repo: ProjectTemplateInstanceRepository | None = None,
        requirement_repo: RequirementRepository | None = None,
    ) -> None:
        self.project_repo = project_repo or ProjectRepository()
        self.template_repo = template_repo or BidTemplatePackageRepository()
        self.instance_repo = instance_repo or ProjectTemplateInstanceRepository()
        self.requirement_repo = requirement_repo or RequirementRepository()

    def ensure_for_project(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        actor: str | None = None,
    ) -> ProjectTemplateInstanceRow:
        existing = self.instance_repo.get_current_for_project(conn, project_id)
        if existing is not None:
            return existing

        project = self.project_repo.get(conn, project_id=project_id)
        if project is None:
            raise ValueError("project not found")
        package_id = getattr(project, "selected_template_package_id", None)
        if package_id is None:
            raise ValueError("project has no selected template package")

        package = self.template_repo.get_by_id(conn, package_id=package_id)
        if package is None:
            raise ValueError("template package not found")
        items = self.template_repo.list_items(conn, package_id=package.id)

        category_code = getattr(project, "category_code", None) or package.category_code
        if not category_code:
            raise ValueError("project/template package has no category_code")

        instance = self.instance_repo.create_instance(
            conn,
            project_id=project_id,
            base_template_package_id=package.id,
            category_code=category_code,
            display_name=f"{getattr(project, 'name', '项目')} - {package.display_name}",
            metadata=self._initial_metadata(project=project, package=package),
        )

        created_chapter_ids: list[str] = []
        for item in items:
            chapter = self.instance_repo.create_chapter(
                conn,
                instance_id=instance.id,
                project_id=project_id,
                source_template_item_id=item.id,
                chapter_code=item.item_code or str(item.sort_order + 1),
                chapter_title=item.item_name,
                volume_type=self._volume_type(package, item),
                sort_order=item.sort_order,
                metadata={
                    "source_template_item_id": str(item.id),
                    "source_relative_path": item.relative_path,
                    "source_render_mode": item.render_mode,
                    "source_item_type": item.item_type,
                },
            )
            created_chapter_ids.append(str(chapter.id))
            for fields in self._default_blocks(project_id=project_id, package=package, item=item):
                self.instance_repo.create_block(conn, chapter.id, fields)

        response_count = self._initialize_requirement_responses(conn, project_id=project_id, instance_id=instance.id)
        self.instance_repo.record_revision(
            conn,
            instance.id,
            "create_instance",
            "clone selected global template package into project template instance",
            {
                "base_template_package_id": str(package.id),
                "chapter_ids": created_chapter_ids,
                "requirement_response_count": response_count,
            },
            actor,
        )
        return instance

    def _initial_metadata(self, *, project: Any, package: BidTemplatePackageRow) -> dict[str, Any]:
        manifest = dict(package.source_manifest or {})
        manifest_metadata = dict(manifest.get("metadata") or {})
        project_metadata = dict(getattr(project, "metadata_json", None) or {})
        return {
            "format_profile": manifest_metadata.get("format_profile") or project_metadata.get("format_profile") or {},
            "seal_units": manifest_metadata.get("seal_units") or project_metadata.get("seal_units") or [],
            "standard_variables": self._standard_variables(project),
            "clarification_reconciliation": {},
        }

    def _standard_variables(self, project: Any) -> dict[str, Any]:
        return {
            "project.name": getattr(project, "name", None),
            "project.tender_no": getattr(project, "tender_no", None),
            "project.tenderer": getattr(project, "employer_name", None),
            "project.bidder": None,
            "project.legal_representative": None,
            "project.manager": None,
            "project.duration": None,
            "project.price": None,
        }

    def _volume_type(self, package: BidTemplatePackageRow, item: BidTemplateItemRow) -> str:
        blob = " ".join([package.package_type, item.item_type, item.item_name, item.relative_path]).lower()
        if "business" in blob or "商务" in blob:
            return "business"
        if "technical" in blob or "技术" in blob:
            return "technical"
        if _PRICING_RE.search(blob):
            return "pricing"
        return package.package_type or "technical"

    def _default_blocks(
        self,
        *,
        project_id: UUID,
        package: BidTemplatePackageRow,
        item: BidTemplateItemRow,
    ) -> list[dict[str, Any]]:
        blob = " ".join([item.item_name, item.filename, item.relative_path, item.item_type, item.render_mode])
        blocks: list[dict[str, Any]] = [
            {
                "project_id": project_id,
                "block_type": "fixed_text",
                "sort_order": 10,
                "label": "固定文本",
                "content_text": "",
                "required": item.is_required,
                "metadata_json": {"source_template_item_id": str(item.id), "source_relative_path": item.relative_path},
            }
        ]
        if self._needs_ai_prompt(item=item, blob=blob):
            blocks.append(
                {
                    "project_id": project_id,
                    "block_type": "ai_prompt",
                    "sort_order": 20,
                    "label": "AI 写作提示",
                    "prompt_text": f"根据招标要求编写《{item.item_name}》章节，必须逐条响应硬性要求。",
                    "required": False,
                    "metadata_json": {"advanced_collapsed_by_default": True},
                }
            )
        if _ASSET_RE.search(blob):
            blocks.append(
                {
                    "project_id": project_id,
                    "block_type": "asset_placeholder",
                    "sort_order": 30,
                    "label": "资料占位",
                    "placeholder_key": self._placeholder_key(item),
                    "asset_type": "qualification_material",
                    "required": item.is_required,
                    "render_options_json": {"asset_filter": {}, "expiry_warning_days": 30},
                }
            )
        blocks.append(
            {
                "project_id": project_id,
                "block_type": "page_break",
                "sort_order": 90,
                "label": "章节分页",
                "required": False,
                "render_options_json": {"break_before": True},
            }
        )
        header_footer = dict((package.source_manifest or {}).get("metadata", {}) or {}).get("header_footer", {})
        blocks.append(
            {
                "project_id": project_id,
                "block_type": "header_footer",
                "sort_order": 100,
                "label": "页眉页脚",
                "required": False,
                "render_options_json": header_footer if isinstance(header_footer, dict) else {},
            }
        )
        if _SEAL_RE.search(blob):
            blocks.append(
                {
                    "project_id": project_id,
                    "block_type": "seal_mark",
                    "sort_order": 110,
                    "label": "签章/签字标记",
                    "required": True,
                    "metadata_json": {
                        "seal_subtype": self._seal_subtype(blob),
                        "required_position": "chapter_end",
                        "applies_to_pages": "current_chapter",
                        "confirmation_required": True,
                    },
                }
            )
        if _PRICING_RE.search(blob):
            blocks.append(
                {
                    "project_id": project_id,
                    "block_type": "excel_attachment",
                    "sort_order": 120,
                    "label": "报价附件边界",
                    "required": item.is_required,
                    "metadata_json": {
                        "volume_type": "pricing",
                        "attachment_type": "external_pricing_workbook",
                        "required_sheet_names": [],
                    },
                }
            )
        return blocks

    def _needs_ai_prompt(self, *, item: BidTemplateItemRow, blob: str) -> bool:
        return item.render_mode in {"ai_written", "generated", "ai"} or bool(_AI_RE.search(blob))

    def _placeholder_key(self, item: BidTemplateItemRow) -> str:
        key = re.sub(r"[^A-Za-z0-9_]+", "_", item.relative_path).strip("_").lower()
        return f"asset.{key or item.id}"

    def _seal_subtype(self, blob: str) -> str:
        if "骑缝章" in blob:
            return "paging_seal"
        if "法定代表人" in blob:
            return "legal_representative_signature"
        if "签字" in blob:
            return "signature"
        return "company_seal"

    def _initialize_requirement_responses(self, conn: Connection, *, project_id: UUID, instance_id: UUID) -> int:
        requirements = self.requirement_repo.list_by_project(conn, project_id=project_id, include_stale=False)
        count = 0
        for requirement in requirements:
            if requirement.get("is_stale"):
                continue
            if requirement.get("review_status") not in {"confirmed", "accepted"} and not requirement.get("human_confirmed"):
                continue
            self.instance_repo.upsert_requirement_response(
                conn,
                instance_id,
                requirement["id"],
                None,
                None,
                {
                    "project_id": project_id,
                    "response_status": "unanswered",
                    "source_type": "tender_requirement",
                    "metadata_json": {"initialized_from_requirement": True},
                },
            )
            count += 1
        return count


    def build_generation_inputs(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        submission_deadline: datetime | None = None,
    ) -> dict[str, Any]:
        instance = self.instance_repo.get_current_for_project(conn, project_id)
        if instance is None or instance.status not in {"ready_for_authoring", "locked_for_generation"}:
            raise ValueError("generation requires a confirmed project template instance")
        if submission_deadline is not None and submission_deadline < datetime.now(timezone.utc) and instance.status != "locked_for_generation":
            raise ValueError("submission deadline has passed; generation is blocked unless template is locked_for_generation")

        chapters: list[dict[str, Any]] = []
        for chapter in self.instance_repo.list_chapters(conn, instance.id):
            if not getattr(chapter, "enabled", True):
                continue
            blocks = [self._block_generation_dict(block) for block in self.instance_repo.list_blocks(conn, chapter.id)]
            chapters.append(
                {
                    "id": str(chapter.id),
                    "chapter_code": chapter.chapter_code,
                    "chapter_title": chapter.chapter_title,
                    "volume_type": chapter.volume_type,
                    "sort_order": chapter.sort_order,
                    "blocks": blocks,
                }
            )
        responses = list(self.instance_repo.list_requirement_responses(conn, instance.id))
        seals = list(self.instance_repo.list_seal_checklist(conn, instance.id))
        unanswered = sum(1 for response in responses if response.response_status == "unanswered")
        pending_seals = sum(1 for seal in seals if seal.confirmation_status != "confirmed")
        metadata = dict(instance.metadata_json or {})
        format_profile = metadata.get("format_profile") or {}
        revision_no = self._latest_revision_no(conn, instance.id)
        return {
            "instance": {
                "id": str(instance.id),
                "version": instance.version,
                "status": instance.status,
                "metadata_json": metadata,
            },
            "chapters": chapters,
            "requirement_responses": [self._response_generation_dict(row) for row in responses],
            "seal_checklist": [self._seal_generation_dict(row) for row in seals],
            "metadata": {
                "template_instance_id": str(instance.id),
                "template_instance_version": instance.version,
                "template_revision_no": revision_no,
                "requirement_response_coverage": {"total": len(responses), "unanswered": unanswered},
                "format_profile_hash": hashlib.sha256(json.dumps(format_profile, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                "seal_checklist_status": {"total": len(seals), "pending": pending_seals},
            },
        }

    def _block_generation_dict(self, block: Any) -> dict[str, Any]:
        return {
            "id": str(block.id),
            "block_type": block.block_type,
            "label": block.label,
            "content_text": getattr(block, "content_text", ""),
            "prompt_text": getattr(block, "prompt_text", ""),
            "placeholder_key": getattr(block, "placeholder_key", None),
            "asset_type": getattr(block, "asset_type", None),
            "required": bool(getattr(block, "required", False)),
            "sort_order": getattr(block, "sort_order", 0),
            "render_options_json": dict(getattr(block, "render_options_json", None) or {}),
            "metadata_json": dict(getattr(block, "metadata_json", None) or {}),
        }

    def _response_generation_dict(self, response: Any) -> dict[str, Any]:
        return {
            "id": str(response.id),
            "requirement_id": str(response.requirement_id),
            "response_status": response.response_status,
            "template_chapter_id": str(response.template_chapter_id) if response.template_chapter_id else None,
            "template_block_id": str(response.template_block_id) if response.template_block_id else None,
            "response_text": getattr(response, "response_text", ""),
        }

    def _seal_generation_dict(self, seal: Any) -> dict[str, Any]:
        return {
            "seal_block_id": str(seal.seal_block_id),
            "confirmation_status": seal.confirmation_status,
        }

    def _latest_revision_no(self, conn: Connection, instance_id: UUID) -> int | None:
        if conn is None:
            return None
        try:
            with conn.cursor() as cur:
                row = cur.execute("SELECT MAX(revision_no) FROM project_template_revision WHERE template_instance_id = %s", (instance_id,)).fetchone()
            return int(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def snapshot(self, instance: ProjectTemplateInstanceRow) -> dict[str, Any]:
        return asdict(instance)


__all__ = ["ProjectTemplateInstanceService"]
