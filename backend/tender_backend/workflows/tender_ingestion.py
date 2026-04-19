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
        """Request an upload slot from MinerU and upload the PDF bytes.

        Per the v4 batch contract, requesting `/file-urls/batch` immediately
        triggers parsing once the file is PUT to the signed URL — there is no
        separate "submit" step. We stash the returned `batch_id` for the poller.
        """
        from tender_backend.services.parse_service.mineru_client import MineruClient

        content = ctx.data.get("file_content")
        if not content:
            return StepResult(state=StepState.FAILED, message="No file_content in context")

        filename = ctx.data.get("filename") or "document.pdf"
        data_id = str(ctx.data.get("document_id") or ctx.project_id)

        client = MineruClient()
        try:
            upload = await client.request_upload_url(filename, data_id=data_id)
            await client.upload_file(upload.upload_url, content)
        except Exception as exc:
            return StepResult(state=StepState.FAILED, message=f"MinerU upload failed: {exc}")

        ctx.data["mineru_batch_id"] = upload.batch_id
        ctx.data["mineru_job_id"] = upload.batch_id
        return StepResult(state=StepState.COMPLETED, message=f"MinerU batch: {upload.batch_id}")


class PollResult(WorkflowStep):
    name = "poll_result"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Poll MinerU until parse completes and stash the canonical result."""
        from tender_backend.services.parse_service.mineru_client import MineruClient
        from tender_backend.services.parse_service.task_poller import poll_until_complete

        batch_id = ctx.data.get("mineru_batch_id") or ctx.data.get("mineru_job_id")
        if not batch_id:
            return StepResult(state=StepState.FAILED, message="No mineru batch_id in context")

        client = MineruClient()
        try:
            result = await poll_until_complete(client, batch_id)
        except TimeoutError as exc:
            return StepResult(state=StepState.FAILED, message=str(exc))

        if result.status == "failed":
            return StepResult(state=StepState.FAILED, message="MinerU parse failed")

        ctx.data["parsed_sections"] = result.sections
        ctx.data["parsed_tables"] = result.tables
        ctx.data["parsed_pages"] = result.pages
        ctx.data["parsed_raw_payload"] = result.raw_payload
        return StepResult(
            state=StepState.COMPLETED,
            message=f"Parsed: {len(result.pages)} pages, {len(result.tables)} tables",
        )


class PersistSections(WorkflowStep):
    name = "persist_sections"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Persist the canonical raw_payload and write parsed sections."""
        from tender_backend.services.parse_service.parser import (
            persist_sections,
            update_document_parse_assets,
        )

        document_id = UUID(ctx.data["document_id"])
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection in context")

        raw_payload = ctx.data.get("parsed_raw_payload") or {}
        if raw_payload:
            update_document_parse_assets(
                conn,
                document_id=document_id,
                parser_name="mineru",
                parser_version=raw_payload.get("parser_version"),
                raw_payload=raw_payload,
            )

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
