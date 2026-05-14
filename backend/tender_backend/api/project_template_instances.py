from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.project_access import require_project_access
from tender_backend.core.security import CurrentUser, get_current_user, require_role, Role
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.project_template_instance_repo import ProjectTemplateInstanceRepository
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.services.project_template_instance_service import ProjectTemplateInstanceService
from tender_backend.services.template_directory_reconciliation_service import (
    DirectoryReconciliationSuggestion,
    TemplateDirectoryReconciliationService,
)
from tender_backend.services.template_edit_propagation_service import TemplateEditPropagationService


router = APIRouter(tags=["project-template-instances"])

_repo = ProjectTemplateInstanceRepository()
_service = ProjectTemplateInstanceService(instance_repo=_repo)
_requirements = RequirementRepository()
_reconciliation = TemplateDirectoryReconciliationService()
_template_edit_propagation = TemplateEditPropagationService()


class ProjectTemplateBlockOut(BaseModel):
    id: UUID
    template_chapter_id: UUID
    project_id: UUID
    block_type: str
    sort_order: int
    label: str
    content_text: str = ""
    prompt_text: str = ""
    placeholder_key: str | None = None
    asset_type: str | None = None
    required: bool = False
    render_options_json: dict[str, Any] = Field(default_factory=dict)
    condition_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectTemplateChapterOut(BaseModel):
    id: UUID
    template_instance_id: UUID
    project_id: UUID
    parent_id: UUID | None = None
    source_template_item_id: UUID | None = None
    chapter_code: str
    chapter_title: str
    volume_type: str
    sort_order: int
    enabled: bool
    chapter_status: str
    tender_requirement_status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    lock_owner: str | None = None
    locked_until: datetime | None = None
    lock_version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    blocks: list[ProjectTemplateBlockOut] = Field(default_factory=list)


class TemplatePromotionProposalOut(BaseModel):
    id: UUID
    template_instance_id: UUID
    base_template_package_id: UUID | None = None
    project_id: UUID
    proposal_status: str
    diff_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    reviewed_by: str | None = None
    created_at: datetime | None = None
    reviewed_at: datetime | None = None


class ProjectTemplateInstanceOut(BaseModel):
    id: UUID
    project_id: UUID
    base_template_package_id: UUID | None = None
    category_code: str
    display_name: str
    status: str
    version: int
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    chapters: list[ProjectTemplateChapterOut] = Field(default_factory=list)
    promotion_proposals: list[TemplatePromotionProposalOut] = Field(default_factory=list)


class DirectoryReconcileBody(BaseModel):
    base_revision_no: int | None = None
    clarification_id: UUID | None = None


class DirectoryReconciliationSuggestionOut(BaseModel):
    id: str
    suggestion_type: str
    severity: str
    source_type: str
    skippable: bool
    required_code: str | None = None
    required_title: str | None = None
    chapter_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DirectoryReconcileOut(BaseModel):
    suggestions: list[DirectoryReconciliationSuggestionOut]
    summary: dict[str, Any]


class ApplyReconciliationBody(BaseModel):
    selected_suggestion_ids: list[str] = Field(default_factory=list)
    skipped_suggestion_ids: list[str] = Field(default_factory=list)
    not_applicable_reasons: dict[str, str] = Field(default_factory=dict)


class ApplyReconciliationOut(BaseModel):
    applied_suggestion_ids: list[str]
    summary: dict[str, Any]

class ProjectTemplateInstanceUpdate(BaseModel):
    display_name: str | None = None
    metadata_json: dict[str, Any] | None = None


class ProjectTemplateChapterUpdate(BaseModel):
    parent_id: UUID | None = None
    chapter_code: str | None = None
    chapter_title: str | None = None
    volume_type: str | None = None
    sort_order: int | None = None
    enabled: bool | None = None
    chapter_status: str | None = None
    tender_requirement_status: str | None = None
    metadata_json: dict[str, Any] | None = None


class ProjectTemplateChapterOrderRow(BaseModel):
    chapter_id: UUID
    parent_id: UUID | None = None
    sort_order: int


class ProjectTemplateChapterReorderBody(BaseModel):
    ordered_tree: list[ProjectTemplateChapterOrderRow]


class ProjectTemplateChapterReorderOut(BaseModel):
    chapters: list[ProjectTemplateChapterOut]


class ProjectTemplateBlockCreate(BaseModel):
    project_id: UUID
    block_type: str
    sort_order: int = 0
    label: str
    content_text: str = ""
    prompt_text: str = ""
    placeholder_key: str | None = None
    asset_type: str | None = None
    required: bool = False
    render_options_json: dict[str, Any] = Field(default_factory=dict)
    condition_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProjectTemplateBlockUpdate(BaseModel):
    block_type: str | None = None
    sort_order: int | None = None
    label: str | None = None
    content_text: str | None = None
    prompt_text: str | None = None
    placeholder_key: str | None = None
    asset_type: str | None = None
    required: bool | None = None
    render_options_json: dict[str, Any] | None = None
    condition_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class ProjectTemplateBlockImpactOut(BaseModel):
    stale_drafts: int = 0
    stale_charts: int = 0
    stale_docx: int = 0
    stale_draft_count: int = 0
    stale_chart_count: int = 0
    stale_export_artifact_count: int = 0


class ProjectTemplateBlockUpdateOut(BaseModel):
    block: ProjectTemplateBlockOut
    revision_no: int
    impact: ProjectTemplateBlockImpactOut


class ProjectTemplateConfirmOut(BaseModel):
    id: UUID
    status: str
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None


class RequirementResponseOut(BaseModel):
    id: UUID
    project_id: UUID
    template_instance_id: UUID
    requirement_id: UUID
    template_chapter_id: UUID | None = None
    template_block_id: UUID | None = None
    response_status: str
    response_text: str = ""
    deviation_note: str = ""
    source_type: str
    source_clarification_id: UUID | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RequirementResponseUpdate(BaseModel):
    response_status: str | None = None
    response_text: str | None = None
    deviation_note: str | None = None
    template_chapter_id: UUID | None = None
    template_block_id: UUID | None = None
    metadata_json: dict[str, Any] | None = None


class SealChecklistItemOut(BaseModel):
    id: UUID
    project_id: UUID
    template_instance_id: UUID
    seal_block_id: UUID
    confirmation_status: str
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    note: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChapterLockBody(BaseModel):
    ttl_seconds: int = Field(default=300, ge=30, le=3600)


class ChapterLockOut(ProjectTemplateChapterOut):
    pass


class SealConfirmBody(BaseModel):
    note: str = ""


def _dump(row: Any) -> dict[str, Any]:
    data = dict(getattr(row, "__dict__", row))
    for key in ["metadata_json", "render_options_json", "condition_json"]:
        if data.get(key) is None:
            data[key] = {}
    return data


def _block_out(row: Any) -> ProjectTemplateBlockOut:
    return ProjectTemplateBlockOut(**_dump(row))


def _chapter_out(row: Any, blocks: list[Any] | None = None) -> ProjectTemplateChapterOut:
    data = _dump(row)
    data["blocks"] = [_block_out(block) for block in (blocks or [])]
    return ProjectTemplateChapterOut(**data)


def _instance_out(conn: Connection, instance: Any) -> ProjectTemplateInstanceOut:
    chapters = []
    for chapter in _repo.list_chapters(conn, instance.id):
        chapters.append(_chapter_out(chapter, _repo.list_blocks(conn, chapter.id)))
    proposals = []
    if hasattr(_repo, "list_promotion_proposals"):
        proposals = [TemplatePromotionProposalOut(**_dump(row)) for row in _repo.list_promotion_proposals(conn, instance.id)]
    data = _dump(instance)
    data["chapters"] = chapters
    data["promotion_proposals"] = proposals
    return ProjectTemplateInstanceOut(**data)


def _find_instance_by_id(conn: Connection, instance_id: UUID) -> Any:
    if hasattr(_repo, "get_by_id"):
        instance = _repo.get_by_id(conn, instance_id)
        if instance is not None:
            return instance
    # Test fakes and legacy repo fallback: infer from chapters/responses where possible.
    for project_id_attr in ("project_id",):
        project_id = getattr(_repo, project_id_attr, None)
        if project_id is not None:
            instance = _repo.get_current_for_project(conn, project_id)
            if instance is not None and instance.id == instance_id:
                return instance
    raise HTTPException(status_code=404, detail="template instance not found")


def _find_block_by_id(conn: Connection, block_id: UUID) -> Any:
    if hasattr(_repo, "get_block_by_id"):
        block = _repo.get_block_by_id(conn, block_id)
        if block is not None:
            return block
    raise HTTPException(status_code=404, detail="block not found")


def _ensure_project_access(conn: Connection, *, project_id: UUID, user: CurrentUser) -> None:
    require_project_access(conn, project_id=project_id, user=user)


@router.get("/projects/{project_id}/template-instance", response_model=ProjectTemplateInstanceOut)
async def get_project_template_instance(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> ProjectTemplateInstanceOut:
    _ensure_project_access(conn, project_id=project_id, user=user)
    instance = _repo.get_current_for_project(conn, project_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="template instance not found")
    return _instance_out(conn, instance)


@router.post("/projects/{project_id}/template-instance", response_model=ProjectTemplateInstanceOut)
async def create_project_template_instance(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectTemplateInstanceOut:
    _ensure_project_access(conn, project_id=project_id, user=user)
    try:
        instance = _service.ensure_for_project(conn, project_id=project_id, actor=user.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _instance_out(conn, instance)


@router.patch("/project-template-instances/{instance_id}", response_model=ProjectTemplateInstanceOut)
async def update_project_template_instance(
    instance_id: UUID,
    payload: ProjectTemplateInstanceUpdate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectTemplateInstanceOut:
    instance = _find_instance_by_id(conn, instance_id)
    _ensure_project_access(conn, project_id=instance.project_id, user=user)
    if not hasattr(_repo, "update_instance"):
        raise HTTPException(status_code=501, detail="instance update not supported")
    updated = _repo.update_instance(conn, instance_id, payload.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="template instance not found")
    return _instance_out(conn, updated)


@router.patch("/project-template-chapters/{chapter_id}", response_model=ProjectTemplateChapterOut)
async def update_project_template_chapter(
    chapter_id: UUID,
    payload: ProjectTemplateChapterUpdate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectTemplateChapterOut:
    chapter = _repo.update_chapter(conn, chapter_id, payload.model_dump(exclude_unset=True))
    if chapter is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    _ensure_project_access(conn, project_id=chapter.project_id, user=user)
    return _chapter_out(chapter, _repo.list_blocks(conn, chapter.id))


@router.post("/project-template-instances/{instance_id}/chapters/reorder", response_model=ProjectTemplateChapterReorderOut)
async def reorder_project_template_chapters(
    instance_id: UUID,
    payload: ProjectTemplateChapterReorderBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectTemplateChapterReorderOut:
    instance = _find_instance_by_id(conn, instance_id)
    _ensure_project_access(conn, project_id=instance.project_id, user=user)
    ordered_tree = [row.model_dump() for row in payload.ordered_tree]
    if hasattr(_repo, "replace_chapter_tree_order"):
        chapters = _repo.replace_chapter_tree_order(conn, instance_id, ordered_tree, actor=user.display_name)
    else:
        _repo.replace_chapter_order(conn, instance_id, [row["chapter_id"] for row in ordered_tree])
        chapters = _repo.list_chapters(conn, instance_id)
    _repo.record_revision(conn, instance_id, "manual_reorder", "manual chapter reorder", {"ordered_tree": ordered_tree}, user.display_name)
    return ProjectTemplateChapterReorderOut(chapters=[_chapter_out(chapter, _repo.list_blocks(conn, chapter.id)) for chapter in chapters])


@router.post("/project-template-chapters/{chapter_id}/blocks", response_model=ProjectTemplateBlockOut)
async def create_project_template_block(
    chapter_id: UUID,
    payload: ProjectTemplateBlockCreate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectTemplateBlockOut:
    _ensure_project_access(conn, project_id=payload.project_id, user=user)
    block = _repo.create_block(conn, chapter_id, payload.model_dump())
    return _block_out(block)


@router.patch("/project-template-blocks/{block_id}", response_model=ProjectTemplateBlockUpdateOut)
async def update_project_template_block(
    block_id: UUID,
    payload: ProjectTemplateBlockUpdate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectTemplateBlockUpdateOut:
    existing = _find_block_by_id(conn, block_id)
    _ensure_project_access(conn, project_id=existing.project_id, user=user)
    with conn.transaction():
        block = _repo.update_block(conn, block_id, payload.model_dump(exclude_unset=True))
        if block is None:
            raise HTTPException(status_code=404, detail="block not found")
        instance = _repo.get_current_for_project(conn, block.project_id)
        if instance is None:
            raise HTTPException(status_code=404, detail="template instance not found")
        revision = _repo.record_revision(
            conn,
            instance.id,
            "template_block_update",
            f"update {block.block_type} block {block.label}",
            {"block_id": str(block.id), "block_type": block.block_type, "fields": payload.model_dump(exclude_unset=True)},
            user.display_name,
        )
        impact = _template_edit_propagation.apply_stale_impact(conn, block=block, revision_no=revision.revision_no, actor=user.display_name)
    return ProjectTemplateBlockUpdateOut(block=_block_out(block), revision_no=revision.revision_no, impact=ProjectTemplateBlockImpactOut(**impact))


@router.delete("/project-template-blocks/{block_id}")
async def delete_project_template_block(
    block_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> dict[str, bool]:
    deleted = _repo.delete_block(conn, block_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="block not found")
    return {"deleted": True}


@router.post("/project-template-instances/{instance_id}/confirm", response_model=ProjectTemplateConfirmOut)
async def confirm_project_template_instance(
    instance_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectTemplateConfirmOut:
    instance = _find_instance_by_id(conn, instance_id)
    _ensure_project_access(conn, project_id=instance.project_id, user=user)
    metadata = dict(instance.metadata_json or {})
    reconciliation = dict(metadata.get("reconciliation") or {})
    if int(reconciliation.get("critical", 0) or 0) > 0:
        raise HTTPException(status_code=400, detail="critical reconciliation issues remain")
    unanswered = [row for row in _repo.list_requirement_responses(conn, instance_id) if row.response_status == "unanswered"]
    if unanswered:
        raise HTTPException(status_code=400, detail="required requirement responses remain unanswered")
    fields = {"status": "ready_for_authoring", "confirmed_by": user.display_name}
    if hasattr(_repo, "confirm_instance"):
        updated = _repo.confirm_instance(conn, instance_id, actor=user.display_name)
    else:
        updated = _repo.update_instance(conn, instance_id, fields)
    return ProjectTemplateConfirmOut(id=updated.id, status=updated.status, confirmed_at=updated.confirmed_at, confirmed_by=updated.confirmed_by)




@router.post("/project-template-instances/{instance_id}/promotion-proposals", response_model=TemplatePromotionProposalOut)
async def create_project_template_promotion_proposal(
    instance_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> TemplatePromotionProposalOut:
    instance = _find_instance_by_id(conn, instance_id)
    _ensure_project_access(conn, project_id=instance.project_id, user=user)
    try:
        proposal = _service.create_promotion_proposal(conn, instance_id=instance_id, actor=user.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TemplatePromotionProposalOut(**_dump(proposal))


@router.get("/project-template-instances/{instance_id}/requirement-responses", response_model=list[RequirementResponseOut])
async def list_requirement_responses(
    instance_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[RequirementResponseOut]:
    instance = _find_instance_by_id(conn, instance_id)
    _ensure_project_access(conn, project_id=instance.project_id, user=user)
    return [RequirementResponseOut(**_dump(row)) for row in _repo.list_requirement_responses(conn, instance_id)]


@router.patch("/project-requirement-responses/{response_id}", response_model=RequirementResponseOut)
async def update_requirement_response(
    response_id: UUID,
    payload: RequirementResponseUpdate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> RequirementResponseOut:
    if not hasattr(_repo, "update_requirement_response"):
        raise HTTPException(status_code=501, detail="requirement response update not supported")
    row = _repo.update_requirement_response(conn, response_id, payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="requirement response not found")
    _ensure_project_access(conn, project_id=row.project_id, user=user)
    return RequirementResponseOut(**_dump(row))


@router.get("/project-template-instances/{instance_id}/seal-checklist", response_model=list[SealChecklistItemOut])
async def list_seal_checklist(
    instance_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[SealChecklistItemOut]:
    instance = _find_instance_by_id(conn, instance_id)
    _ensure_project_access(conn, project_id=instance.project_id, user=user)
    return [SealChecklistItemOut(**_dump(row)) for row in _repo.list_seal_checklist(conn, instance_id)]


@router.post("/project-template-instances/{instance_id}/seal-checklist/{seal_block_id}/confirm", response_model=SealChecklistItemOut)
async def confirm_seal_item(
    instance_id: UUID,
    seal_block_id: UUID,
    payload: SealConfirmBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> SealChecklistItemOut:
    row = _repo.confirm_seal_item(conn, instance_id, seal_block_id, user.display_name, payload.note)
    return SealChecklistItemOut(**_dump(row))


@router.post("/project-template-chapters/{chapter_id}/lock", response_model=ChapterLockOut)
async def lock_project_template_chapter(
    chapter_id: UUID,
    payload: ChapterLockBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ChapterLockOut:
    body = payload or ChapterLockBody()
    chapter = _repo.try_lock_chapter(conn, chapter_id, user.display_name, body.ttl_seconds)
    if chapter is None:
        raise HTTPException(status_code=409, detail="chapter is locked by another actor")
    _ensure_project_access(conn, project_id=chapter.project_id, user=user)
    return ChapterLockOut(**_chapter_out(chapter, _repo.list_blocks(conn, chapter.id)).model_dump())


@router.delete("/project-template-chapters/{chapter_id}/lock")
async def release_project_template_chapter_lock(
    chapter_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> dict[str, bool]:
    return {"released": _repo.release_chapter_lock(conn, chapter_id, user.display_name)}


@router.post("/projects/{project_id}/template-instance/reconcile-directory", response_model=DirectoryReconcileOut)
async def reconcile_project_template_directory(
    project_id: UUID,
    payload: DirectoryReconcileBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> DirectoryReconcileOut:
    _ensure_project_access(conn, project_id=project_id, user=user)
    instance = _repo.get_current_for_project(conn, project_id)
    if instance is None:
        try:
            instance = _service.ensure_for_project(conn, project_id=project_id, actor=user.display_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    requirements = _requirements.list_by_project(conn, project_id=project_id, include_stale=False)
    chapters = _repo.list_chapters(conn, instance.id)
    suggestions = _reconciliation.build_suggestions(requirements, chapters)
    summary = _reconciliation.summary(suggestions)
    metadata = dict(instance.metadata_json or {})
    metadata["reconciliation"] = summary
    if payload and payload.clarification_id:
        metadata["clarification_reconciliation"] = {
            "clarification_id": str(payload.clarification_id),
            "unresolved_impact_count": len([item for item in suggestions if item.source_type == "tender_addendum"]),
        }
    if hasattr(_repo, "update_instance"):
        _repo.update_instance(conn, instance.id, {"metadata_json": metadata})
        # Keep in-memory fakes coherent when they mutate by replacement.
        refreshed = _repo.get_current_for_project(conn, project_id)
        if refreshed is not None:
            instance = refreshed
    return DirectoryReconcileOut(
        suggestions=[DirectoryReconciliationSuggestionOut(**item.__dict__) for item in suggestions],
        summary=summary,
    )


@router.post("/projects/{project_id}/template-instance/apply-reconciliation", response_model=ApplyReconciliationOut)
async def apply_project_template_directory_reconciliation(
    project_id: UUID,
    payload: ApplyReconciliationBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ApplyReconciliationOut:
    _ensure_project_access(conn, project_id=project_id, user=user)
    instance = _repo.get_current_for_project(conn, project_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="template instance not found")
    requirements = _requirements.list_by_project(conn, project_id=project_id, include_stale=False)
    suggestions = _reconciliation.build_suggestions(requirements, _repo.list_chapters(conn, instance.id))
    try:
        _reconciliation.validate_apply_selection(
            suggestions,
            skipped_suggestion_ids=payload.skipped_suggestion_ids,
            not_applicable_reasons=payload.not_applicable_reasons,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    selected = set(payload.selected_suggestion_ids)
    applied = [item for item in suggestions if item.id in selected]
    summary = _reconciliation.summary(suggestions)
    metadata = dict(instance.metadata_json or {})
    metadata["reconciliation"] = {**summary, "applied_suggestion_ids": [item.id for item in applied]}
    if hasattr(_repo, "update_instance"):
        _repo.update_instance(conn, instance.id, {"metadata_json": metadata})
    _repo.record_revision(
        conn,
        instance.id,
        "apply_reconciliation",
        "apply tender directory reconciliation suggestions",
        {"applied_suggestion_ids": [item.id for item in applied]},
        user.display_name,
    )
    return ApplyReconciliationOut(applied_suggestion_ids=[item.id for item in applied], summary=summary)
