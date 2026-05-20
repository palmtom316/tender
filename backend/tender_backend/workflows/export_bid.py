"""export_bid workflow — export with 3-gate validation.

Gates: (1) all veto requirements confirmed, (2) no P0/P1 issues unresolved,
       (3) format validation passes.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import structlog

from tender_backend.workflows.base import (
    BaseWorkflow,
    StepResult,
    WorkflowContext,
    WorkflowStep,
)
from tender_backend.workflows.registry import register_workflow
from tender_backend.workflows.states import StepState

logger = structlog.stdlib.get_logger(__name__)


class CheckVetoGate(WorkflowStep):
    name = "check_veto_gate"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from tender_backend.db.repositories.requirement_repo import RequirementRepository
        repo = RequirementRepository()
        count = repo.unconfirmed_veto_count(conn, project_id=UUID(ctx.project_id))
        if count > 0:
            return StepResult(
                state=StepState.FAILED,
                message=f"Export blocked: {count} unconfirmed veto requirements",
            )
        return StepResult(state=StepState.COMPLETED, message="Veto gate passed")


class CheckReviewGate(WorkflowStep):
    name = "check_review_gate"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from tender_backend.services.review_service.review_engine import get_blocking_issues
        blocking = get_blocking_issues(conn, project_id=UUID(ctx.project_id))
        if blocking:
            return StepResult(
                state=StepState.FAILED,
                message=f"Export blocked: {len(blocking)} unresolved P0/P1 issues",
            )
        return StepResult(state=StepState.COMPLETED, message="Review gate passed")


class CheckFormatGate(WorkflowStep):
    name = "check_format_gate"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        # Format validation is optional in Phase 1
        template = ctx.data.get("template_path")
        if not template:
            return StepResult(state=StepState.COMPLETED, message="No template to validate, skipped")
        from tender_backend.services.export_service.format_validator import validate_format, FormatRequirements
        reqs = FormatRequirements(page_size="A4")
        issues = validate_format(template, reqs)
        if issues:
            ctx.data["format_issues"] = [
                {"field": i.field, "expected": i.expected, "actual": i.actual}
                for i in issues
            ]
            # Format issues are warnings, not blockers in Phase 1
            logger.warning("format_issues_found", count=len(issues))
        return StepResult(state=StepState.COMPLETED, message=f"Format check: {len(issues)} issues")


class RenderDocx(WorkflowStep):
    name = "render_docx"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from tender_backend.services.export_gate_service import build_export_gate_state
        from tender_backend.services.export_service.docx_exporter import (
            EXPORT_MODE_SINGLE_DOCX,
            EXPORT_MODES,
            render_export,
        )
        template_name = ctx.data.get("template_name", "default_technical_bid.docx")
        mode = ctx.data.get("export_mode", EXPORT_MODE_SINGLE_DOCX)
        if mode not in EXPORT_MODES:
            return StepResult(state=StepState.FAILED, message=f"unsupported export mode: {mode}")
        gate_state = build_export_gate_state(conn, project_id=UUID(ctx.project_id))
        if not gate_state.get("can_export"):
            return StepResult(
                state=StepState.FAILED,
                message=f"Export blocked by final gate: {gate_state.get('gates')}",
            )
        from tender_backend.services.project_template_instance_service import ProjectTemplateInstanceService
        try:
            ctx.data["project_template_generation_inputs"] = ProjectTemplateInstanceService().build_generation_inputs(
                conn, project_id=UUID(ctx.project_id)
            )
        except (AttributeError, ValueError):
            ctx.data["project_template_generation_inputs"] = {"metadata": {}, "chapters": []}
        try:
            output = render_export(
                conn,
                project_id=UUID(ctx.project_id),
                mode=mode,
                template_name=template_name,
            )
            ctx.data["docx_path"] = str(output)
            ctx.data["export_mode"] = mode
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            return StepResult(state=StepState.FAILED, message=str(exc))
        return StepResult(state=StepState.COMPLETED, message=f"Export rendered: {output}")


class ConvertToPdf(WorkflowStep):
    name = "convert_to_pdf"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        from pathlib import Path
        from tender_backend.services.export_service.docx_exporter import EXPORT_MODE_SINGLE_DOCX
        if ctx.data.get("export_mode", EXPORT_MODE_SINGLE_DOCX) != EXPORT_MODE_SINGLE_DOCX:
            ctx.data["pdf_path"] = None
            return StepResult(state=StepState.COMPLETED, message="PDF conversion skipped for non-single-docx mode")
        docx_path = ctx.data.get("docx_path")
        if not docx_path:
            return StepResult(state=StepState.FAILED, message="No DOCX path")
        from tender_backend.services.export_service.pdf_exporter import convert_docx_to_pdf
        try:
            pdf_path = convert_docx_to_pdf(Path(docx_path))
            ctx.data["pdf_path"] = str(pdf_path)
        except RuntimeError as exc:
            # PDF conversion is optional
            logger.warning("pdf_conversion_skipped", error=str(exc))
            ctx.data["pdf_path"] = None
        return StepResult(state=StepState.COMPLETED, message="PDF conversion attempted")


class SaveExportRecord(WorkflowStep):
    name = "save_export_record"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        export_key = ctx.data.get("docx_path", "")
        template_name = ctx.data.get("export_mode") or ctx.data.get("template_name", "default")
        conn.execute(
            """
            INSERT INTO export_record (id, project_id, status, template_name, export_key)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (uuid4(), UUID(ctx.project_id), "completed", template_name, export_key),
        )
        conn.commit()
        return StepResult(state=StepState.COMPLETED, message="Export record saved")


@register_workflow
class ExportBidWorkflow(BaseWorkflow):
    workflow_name = "export_bid"

    def _define_steps(self) -> list[WorkflowStep]:
        return [
            CheckVetoGate(),
            CheckReviewGate(),
            CheckFormatGate(),
            RenderDocx(),
            ConvertToPdf(),
            SaveExportRecord(),
        ]
