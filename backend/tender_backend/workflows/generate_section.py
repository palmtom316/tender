"""generate_section workflow — chapter generation pipeline.

Steps: load_project_facts → load_section_requirements → search_clauses
       → search_sections → assemble_evidence_pack → llm_generate_outline
       → human_confirm_outline (suspend) → llm_generate_section → save_draft
"""

from __future__ import annotations

import structlog

from tender_backend.services.technical_bid_writer import TechnicalBidWriter

from tender_backend.workflows.base import (
    BaseWorkflow,
    StepResult,
    WorkflowContext,
    WorkflowStep,
)
from tender_backend.workflows.registry import register_workflow
from tender_backend.workflows.states import StepState

logger = structlog.stdlib.get_logger(__name__)


class LoadProjectFacts(WorkflowStep):
    name = "load_project_facts"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT fact_key, fact_value FROM project_fact WHERE project_id = %s",
                (ctx.project_id,),
            ).fetchall()
        ctx.data["project_facts"] = {r["fact_key"]: r["fact_value"] for r in rows}
        return StepResult(state=StepState.COMPLETED, message=f"Loaded {len(rows)} facts")


class LoadSectionRequirements(WorkflowStep):
    name = "load_section_requirements"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT *
                FROM project_requirement
                WHERE project_id = %s
                  AND COALESCE(ignored_for_pricing, false) = false
                  AND COALESCE(is_stale, false) = false
                  AND COALESCE(review_status, 'pending') <> 'rejected'
                ORDER BY category, created_at
                """,
                (ctx.project_id,),
            ).fetchall()
        ctx.data["requirements"] = rows
        ctx.data["requirement_priority_policy"] = "tender_extracted_requirements_override_template"
        return StepResult(state=StepState.COMPLETED, message=f"Loaded {len(rows)} requirements")


class SearchRelatedClauses(WorkflowStep):
    name = "search_clauses"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        section_name = ctx.data.get("section_name", "")
        if not section_name:
            ctx.data["matched_clauses"] = []
            return StepResult(state=StepState.COMPLETED, message="No section name, skipped")
        from tender_backend.services.search_service.query_service import search_clauses
        results = await search_clauses(section_name, top_k=10)
        ctx.data["matched_clauses"] = results
        return StepResult(state=StepState.COMPLETED, message=f"Found {len(results)} clauses")


class LoadRequirementMatches(WorkflowStep):
    name = "load_requirement_matches"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            ctx.data["requirement_matches"] = []
            return StepResult(state=StepState.COMPLETED, message="No DB connection, skipped matches")
        from tender_backend.db.repositories.requirement_match_repo import RequirementMatchRepository
        rows = RequirementMatchRepository().list_by_project(conn, project_id=ctx.project_id)
        ctx.data["requirement_matches"] = rows
        return StepResult(state=StepState.COMPLETED, message=f"Loaded {len(rows)} requirement matches")


class LoadBidChapterOutline(WorkflowStep):
    name = "load_bid_chapter_outline"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        chapter_code = ctx.data.get("chapter_code")
        if conn is None or not chapter_code:
            ctx.data["bid_chapter"] = None
            ctx.data["bid_chapter_requirements"] = []
            return StepResult(state=StepState.COMPLETED, message="No chapter outline context, skipped")
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            chapter = cur.execute(
                """
                SELECT bc.*
                FROM bid_chapter bc
                JOIN bid_outline bo ON bo.id = bc.bid_outline_id
                WHERE bc.project_id = %s
                  AND bc.chapter_code = %s
                ORDER BY bo.created_at DESC, bc.sort_order
                LIMIT 1
                """,
                (ctx.project_id, chapter_code),
            ).fetchone()
            if chapter is None:
                ctx.data["bid_chapter"] = None
                ctx.data["bid_chapter_requirements"] = []
                return StepResult(state=StepState.COMPLETED, message="No bid chapter outline found")
            mapped_requirements = cur.execute(
                """
                SELECT pr.*, bcr.mapping_reason, bcr.priority_level
                FROM bid_chapter_requirement bcr
                JOIN project_requirement pr ON pr.id = bcr.requirement_id
                WHERE bcr.bid_chapter_id = %s
                ORDER BY bcr.priority_level, pr.created_at
                """,
                (chapter["id"],),
            ).fetchall()
        ctx.data["bid_chapter"] = dict(chapter)
        ctx.data["bid_chapter_requirements"] = [dict(row) for row in mapped_requirements]
        return StepResult(
            state=StepState.COMPLETED,
            message=f"Loaded bid chapter outline with {len(mapped_requirements)} mapped requirements",
        )


class SearchReferenceSections(WorkflowStep):
    name = "search_sections"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        section_name = ctx.data.get("section_name", "")
        if not section_name:
            ctx.data["reference_sections"] = []
            return StepResult(state=StepState.COMPLETED, message="No section name, skipped")
        from tender_backend.services.search_service.query_service import search_sections
        results = await search_sections(section_name, top_k=5)
        ctx.data["reference_sections"] = results
        return StepResult(state=StepState.COMPLETED, message=f"Found {len(results)} reference sections")


class AssembleEvidencePack(WorkflowStep):
    name = "assemble_evidence_pack"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        evidence = {
            "project_facts": ctx.data.get("project_facts", {}),
            "requirements": ctx.data.get("requirements", []),
            "requirement_matches": ctx.data.get("requirement_matches", []),
            "bid_chapter": ctx.data.get("bid_chapter"),
            "bid_chapter_requirements": ctx.data.get("bid_chapter_requirements", []),
            "requirement_priority_policy": ctx.data.get("requirement_priority_policy"),
            "scoring_criteria": ctx.data.get("scoring_criteria", []),
            "matched_clauses": ctx.data.get("matched_clauses", []),
            "reference_sections": ctx.data.get("reference_sections", []),
        }
        ctx.data["evidence_pack"] = evidence
        return StepResult(state=StepState.COMPLETED, message="Evidence pack assembled")


class LLMGenerateOutline(WorkflowStep):
    name = "llm_generate_outline"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        ctx.data["generated_outline"] = None
        return StepResult(state=StepState.COMPLETED, message="Outline generation delegated to TechnicalBidWriter")


class HumanConfirmOutline(WorkflowStep):
    name = "human_confirm_outline"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        """Suspend workflow for human to review and adjust the outline."""
        return StepResult(
            state=StepState.COMPLETED,
            message="Outline confirmation point",
            suspend=True,
        )


class LLMGenerateSection(WorkflowStep):
    name = "llm_generate_section"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        chapter_id = ctx.data.get("chapter_id") or (ctx.data.get("bid_chapter") or {}).get("id")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        if chapter_id is None:
            return StepResult(state=StepState.FAILED, message="No technical chapter id")
        result = TechnicalBidWriter().generate_chapter(
            conn,
            project_id=ctx.project_id,
            chapter_id=chapter_id,
            created_by=ctx.data.get("created_by"),
            rewrite_note=ctx.data.get("rewrite_note"),
        )
        ctx.data["generated_draft"] = result.get("draft")
        ctx.data["generation_run"] = result.get("run")
        ctx.data["generated_content"] = (result.get("draft") or {}).get("content_md", "")
        return StepResult(state=StepState.COMPLETED, message="Section content generated by TechnicalBidWriter")


class SaveDraft(WorkflowStep):
    name = "save_draft"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        draft = ctx.data.get("generated_draft")
        if draft:
            return StepResult(state=StepState.COMPLETED, message="Draft already saved by TechnicalBidWriter")
        return StepResult(state=StepState.FAILED, message="No generated draft to save")


@register_workflow
class GenerateSectionWorkflow(BaseWorkflow):
    workflow_name = "generate_section"

    def _define_steps(self) -> list[WorkflowStep]:
        return [
            LoadProjectFacts(),
            LoadSectionRequirements(),
            LoadRequirementMatches(),
            LoadBidChapterOutline(),
            SearchRelatedClauses(),
            SearchReferenceSections(),
            AssembleEvidencePack(),
            LLMGenerateOutline(),
            HumanConfirmOutline(),
            LLMGenerateSection(),
            SaveDraft(),
        ]
