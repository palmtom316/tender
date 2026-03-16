"""generate_section workflow — chapter generation pipeline.

Steps: load_project_facts → load_section_requirements → search_clauses
       → search_sections → assemble_evidence_pack → llm_generate_outline
       → human_confirm_outline (suspend) → llm_generate_section → save_draft
"""

from __future__ import annotations

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
                "SELECT * FROM project_requirement WHERE project_id = %s ORDER BY category, created_at",
                (ctx.project_id,),
            ).fetchall()
        ctx.data["requirements"] = rows
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
            "scoring_criteria": ctx.data.get("scoring_criteria", []),
            "matched_clauses": ctx.data.get("matched_clauses", []),
            "reference_sections": ctx.data.get("reference_sections", []),
        }
        ctx.data["evidence_pack"] = evidence
        return StepResult(state=StepState.COMPLETED, message="Evidence pack assembled")


class LLMGenerateOutline(WorkflowStep):
    name = "llm_generate_outline"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        # In production, calls AI Gateway with evidence pack + prompt template
        section_name = ctx.data.get("section_name", "未知章节")
        ctx.data["generated_outline"] = f"# {section_name}\n\n## 1. 编制说明\n## 2. 工程概况\n## 3. 施工方案\n## 4. 质量保证措施\n## 5. 安全文明施工"
        return StepResult(state=StepState.COMPLETED, message="Outline generated")


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
        # In production, calls AI Gateway with outline + evidence pack
        section_name = ctx.data.get("section_name", "未知章节")
        outline = ctx.data.get("generated_outline", "")
        ctx.data["generated_content"] = f"{outline}\n\n（AI 生成的 {section_name} 正文内容占位符）"
        return StepResult(state=StepState.COMPLETED, message="Section content generated")


class SaveDraft(WorkflowStep):
    name = "save_draft"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        import uuid
        chapter_code = ctx.data.get("chapter_code", "unknown")
        content = ctx.data.get("generated_content", "")
        conn.execute(
            """
            INSERT INTO chapter_draft (id, project_id, chapter_code, content_md)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (project_id, chapter_code)
            DO UPDATE SET content_md = EXCLUDED.content_md, updated_at = now()
            """,
            (uuid.uuid4().hex, ctx.project_id, chapter_code, content),
        )
        conn.commit()
        return StepResult(state=StepState.COMPLETED, message=f"Draft saved: {chapter_code}")


@register_workflow
class GenerateSectionWorkflow(BaseWorkflow):
    workflow_name = "generate_section"

    def _define_steps(self) -> list[WorkflowStep]:
        return [
            LoadProjectFacts(),
            LoadSectionRequirements(),
            SearchRelatedClauses(),
            SearchReferenceSections(),
            AssembleEvidencePack(),
            LLMGenerateOutline(),
            HumanConfirmOutline(),
            LLMGenerateSection(),
            SaveDraft(),
        ]
