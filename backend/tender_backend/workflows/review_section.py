"""review_section workflow — reviews chapter drafts for quality and compliance.

Steps: load_drafts → load_requirements → rule_review → model_review
       → build_compliance_matrix → persist_issues
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


class LoadDrafts(WorkflowStep):
    name = "load_drafts"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM chapter_draft WHERE project_id = %s",
                (ctx.project_id,),
            ).fetchall()
        ctx.data["drafts"] = rows
        return StepResult(state=StepState.COMPLETED, message=f"Loaded {len(rows)} drafts")


class LoadReviewContext(WorkflowStep):
    name = "load_review_context"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            reqs = cur.execute(
                "SELECT * FROM project_requirement WHERE project_id = %s",
                (ctx.project_id,),
            ).fetchall()
            facts = cur.execute(
                "SELECT fact_key, fact_value FROM project_fact WHERE project_id = %s",
                (ctx.project_id,),
            ).fetchall()
        ctx.data["requirements"] = reqs
        ctx.data["facts"] = {r["fact_key"]: r["fact_value"] for r in facts}
        return StepResult(state=StepState.COMPLETED, message="Review context loaded")


class RuleReview(WorkflowStep):
    name = "rule_review"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        from tender_backend.services.review_service.review_engine import review_draft
        all_issues = []
        for draft in ctx.data.get("drafts", []):
            issues = review_draft(
                content=draft["content_md"],
                chapter_code=draft["chapter_code"],
                requirements=ctx.data.get("requirements", []),
                facts=ctx.data.get("facts", {}),
            )
            all_issues.extend(issues)
        ctx.data["review_issues"] = all_issues
        return StepResult(state=StepState.COMPLETED, message=f"Found {len(all_issues)} issues")


class ModelReview(WorkflowStep):
    name = "model_review"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        # In production, calls AI Gateway for content quality review
        # For now, pass through
        return StepResult(state=StepState.COMPLETED, message="Model review placeholder")


class BuildComplianceMatrix(WorkflowStep):
    name = "build_compliance_matrix"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from tender_backend.services.review_service.compliance_matrix import build_compliance_matrix
        entries = build_compliance_matrix(conn, project_id=UUID(ctx.project_id))
        ctx.data["compliance_matrix"] = [
            {"requirement_id": e.requirement_id, "requirement_title": e.requirement_title,
             "category": e.category, "chapter_code": e.chapter_code, "coverage": e.coverage}
            for e in entries
        ]
        return StepResult(state=StepState.COMPLETED, message=f"Matrix: {len(entries)} entries")


class PersistIssues(WorkflowStep):
    name = "persist_issues"

    async def execute(self, ctx: WorkflowContext) -> StepResult:
        conn = ctx.data.get("_db_conn")
        if conn is None:
            return StepResult(state=StepState.FAILED, message="No DB connection")
        from tender_backend.services.review_service.review_engine import persist_review_issues
        issues = ctx.data.get("review_issues", [])
        count = persist_review_issues(conn, project_id=UUID(ctx.project_id), issues=issues)
        return StepResult(state=StepState.COMPLETED, message=f"Persisted {count} issues")


@register_workflow
class ReviewSectionWorkflow(BaseWorkflow):
    workflow_name = "review_section"

    def _define_steps(self) -> list[WorkflowStep]:
        return [
            LoadDrafts(),
            LoadReviewContext(),
            RuleReview(),
            ModelReview(),
            BuildComplianceMatrix(),
            PersistIssues(),
        ]
