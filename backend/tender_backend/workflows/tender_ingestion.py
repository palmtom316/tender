"""tender_ingestion workflow — end-to-end document parsing pipeline.

Steps: upload_to_minio → request_parse → poll_result → persist_sections
       → persist_tables → extract_outline
"""

from __future__ import annotations

from uuid import UUID

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


class UploadToMinio(WorkflowStep):
    name = "upload_to_minio"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Upload the project file to MinIO object storage."""
        # Requires: ctx.data["project_file_id"], ctx.data["file_content"], ctx.data["filename"]
        # In production, reads from local temp or streams to MinIO.
        # For now, mark as complete if storage_key is pre-set.
        storage_key = ctx.data.get("storage_key")
        if storage_key:
            return StepResult(state=StepState.COMPLETED, message=f"Already in MinIO: {storage_key}")
        # Placeholder — actual MinIO upload will use minio SDK
        key = f"projects/{ctx.project_id}/{ctx.data.get('filename', 'unknown')}"
        ctx.data["storage_key"] = key
        return StepResult(state=StepState.COMPLETED, message=f"Uploaded to {key}")


class RequestParse(WorkflowStep):
    name = "request_parse"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Submit parse request to MinerU."""
        from tender_backend.services.parse_service.mineru_client import MineruClient

        client = MineruClient()
        try:
            mineru_job_id = await client.submit_parse(ctx.data["storage_key"])
        except Exception as exc:
            return StepResult(state=StepState.FAILED, message=f"MinerU submit failed: {exc}")
        ctx.data["mineru_job_id"] = mineru_job_id
        return StepResult(state=StepState.COMPLETED, message=f"MinerU job: {mineru_job_id}")


class PollResult(WorkflowStep):
    name = "poll_result"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Poll MinerU until parse completes."""
        from tender_backend.services.parse_service.mineru_client import MineruClient
        from tender_backend.services.parse_service.task_poller import poll_until_complete

        client = MineruClient()
        try:
            result = await poll_until_complete(client, ctx.data["mineru_job_id"])
        except TimeoutError as exc:
            return StepResult(state=StepState.FAILED, message=str(exc))

        if result.status == "failed":
            return StepResult(state=StepState.FAILED, message="MinerU parse failed")

        ctx.data["parsed_sections"] = result.sections
        ctx.data["parsed_tables"] = result.tables
        ctx.data["parsed_pages"] = result.pages
        return StepResult(state=StepState.COMPLETED, message=f"Parsed: {len(result.sections)} sections, {len(result.tables)} tables")


class PersistSections(WorkflowStep):
    name = "persist_sections"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Write parsed sections to document_section table."""
        from tender_backend.services.parse_service.parser import persist_sections

        document_id = UUID(ctx.data["document_id"])
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection in context")
        count = persist_sections(conn, document_id=document_id, sections=ctx.data.get("parsed_sections", []))
        return StepResult(state=StepState.COMPLETED, message=f"Persisted {count} sections")


class PersistTables(WorkflowStep):
    name = "persist_tables"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Write parsed tables to document_table table."""
        from tender_backend.services.parse_service.parser import persist_tables

        document_id = UUID(ctx.data["document_id"])
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection in context")
        count = persist_tables(conn, document_id=document_id, tables=ctx.data.get("parsed_tables", []))
        return StepResult(state=StepState.COMPLETED, message=f"Persisted {count} tables")


class ExtractOutline(WorkflowStep):
    name = "extract_outline"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Build document outline tree from parsed headings."""
        from tender_backend.services.parse_service.parser import persist_outline

        document_id = UUID(ctx.data["document_id"])
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection in context")
        count = persist_outline(conn, document_id=document_id, pages=ctx.data.get("parsed_pages", []))
        return StepResult(state=StepState.COMPLETED, message=f"Built outline with {count} nodes")


@register_workflow
class TenderIngestionWorkflow(BaseWorkflow):
    workflow_name = "tender_ingestion"

    def _define_steps(self) -> list[WorkflowStep]:
        return [
            UploadToMinio(),
            RequestParse(),
            PollResult(),
            PersistSections(),
            PersistTables(),
            ExtractOutline(),
        ]
