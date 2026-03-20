"""standard_ingestion workflow — parse standard PDF, build clause tree, index to OpenSearch.

Steps: parse_standard_pdf → build_clause_tree → tag_clauses → index_to_opensearch
"""

from __future__ import annotations

from uuid import UUID

import structlog
from psycopg.rows import dict_row

from tender_backend.db.pool import get_pool
from tender_backend.core.config import get_settings
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.layout_compressor import compress_sections
from tender_backend.services.norm_service.prompt_builder import build_prompt
from tender_backend.services.norm_service.scope_splitter import split_into_scopes
from tender_backend.services.norm_service.tree_builder import build_tree, link_commentary, validate_tree
from tender_backend.tools.reindex_standard_clauses import build_clause_index_docs
from tender_backend.workflows.base import (
    BaseWorkflow,
    StepResult,
    WorkflowContext,
    WorkflowStep,
)
from tender_backend.workflows.registry import register_workflow
from tender_backend.workflows.states import StepState

logger = structlog.stdlib.get_logger(__name__)

_std_repo = StandardRepository()


def _get_conn():
    settings = get_settings()
    pool = get_pool(database_url=settings.database_url)
    return pool.connection()


class ParseStandardPdf(WorkflowStep):
    name = "parse_standard_pdf"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Check that document sections are available after MinerU parsing."""
        document_id = ctx.data.get("document_id")
        if not document_id:
            return StepResult(state=StepState.FAILED, message="No document_id in context")

        with _get_conn() as conn:
            with conn.cursor() as cur:
                row = cur.execute(
                    "SELECT count(*) FROM document_section WHERE document_id = %s",
                    (document_id,),
                ).fetchone()
                count = row[0] if row else 0

        if count == 0:
            return StepResult(
                state=StepState.FAILED,
                message=f"No sections found for document {document_id}. Run MinerU parse first.",
            )

        ctx.data["section_count"] = count
        return StepResult(
            state=StepState.COMPLETED,
            message=f"Standard PDF parsed: {count} sections for doc {document_id}",
        )


class BuildClauseTree(WorkflowStep):
    name = "build_clause_tree"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Compress sections → split scopes → store in context for AI processing."""
        standard_id = ctx.data.get("standard_id")
        document_id = ctx.data.get("document_id")
        if not standard_id:
            return StepResult(state=StepState.FAILED, message="No standard_id in context")

        with _get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                sections = cur.execute(
                    """SELECT id, section_code, title, level, text,
                              page_start, page_end
                       FROM document_section
                       WHERE document_id = %s
                       ORDER BY page_start, level, section_code""",
                    (document_id,),
                ).fetchall()

        windows = compress_sections(sections)
        scopes = split_into_scopes(windows)

        ctx.data["scopes"] = [
            {
                "scope_type": s.scope_type,
                "chapter_label": s.chapter_label,
                "text": s.text,
                "page_start": s.page_start,
                "page_end": s.page_end,
            }
            for s in scopes
        ]
        ctx.data["clause_count"] = 0  # Will be updated after AI processing

        return StepResult(
            state=StepState.COMPLETED,
            message=f"Built {len(scopes)} scopes from {len(sections)} sections",
        )


class TagClauses(WorkflowStep):
    name = "tag_clauses"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Process each scope through AI Gateway to extract and tag clauses."""
        import json
        import time

        from tender_backend.services.norm_service.norm_processor import _call_ai_gateway, _parse_llm_json
        from tender_backend.services.norm_service.scope_splitter import ProcessingScope

        standard_id = ctx.data.get("standard_id")
        scopes_data = ctx.data.get("scopes", [])
        if not scopes_data:
            return StepResult(state=StepState.COMPLETED, message="No scopes to process")

        all_entries: list[dict] = []
        with _get_conn() as conn:
            for i, sd in enumerate(scopes_data):
                scope = ProcessingScope(
                    scope_type=sd["scope_type"],
                    chapter_label=sd["chapter_label"],
                    text=sd["text"],
                    page_start=sd["page_start"],
                    page_end=sd["page_end"],
                )
                prompt = build_prompt(scope)
                raw = _call_ai_gateway(conn, prompt, scope.chapter_label)
                entries = _parse_llm_json(raw)

                for entry in entries:
                    entry["clause_type"] = scope.scope_type
                    if entry.get("page_start") is None:
                        entry["page_start"] = scope.page_start

                all_entries.extend(entries)
                if i < len(scopes_data) - 1:
                    time.sleep(2)

        # Build tree and persist
        clauses = build_tree(all_entries, UUID(standard_id))
        clauses = link_commentary(clauses)
        validate_tree(clauses)

        with _get_conn() as conn:
            _std_repo.delete_clauses(conn, UUID(standard_id))
            inserted = _std_repo.bulk_create_clauses(conn, clauses)
            _std_repo.update_processing_status(conn, UUID(standard_id), "completed")

        ctx.data["clause_count"] = inserted
        ctx.data["clauses_to_index"] = clauses

        return StepResult(
            state=StepState.COMPLETED,
            message=f"Extracted and tagged {inserted} clauses from {len(scopes_data)} scopes",
        )


class IndexToOpenSearch(WorkflowStep):
    name = "index_to_opensearch"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Index standard clauses to OpenSearch clause_index."""
        from tender_backend.services.search_service.index_manager import IndexManager

        manager = IndexManager()
        clauses = ctx.data.get("clauses_to_index", [])
        if not clauses:
            return StepResult(state=StepState.COMPLETED, message="No clauses to index")

        docs = build_clause_index_docs(
            {
                "id": UUID(str(ctx.data.get("standard_id"))),
                "standard_code": ctx.data.get("standard_code"),
                "standard_name": ctx.data.get("standard_name"),
                "specialty": ctx.data.get("specialty"),
            },
            clauses,
        )

        count = await manager.bulk_index("clause_index", docs)
        return StepResult(state=StepState.COMPLETED, message=f"Indexed {count} clauses")


@register_workflow
class StandardIngestionWorkflow(BaseWorkflow):
    workflow_name = "standard_ingestion"

    def _define_steps(self) -> list[WorkflowStep]:
        return [
            ParseStandardPdf(),
            BuildClauseTree(),
            TagClauses(),
            IndexToOpenSearch(),
        ]
