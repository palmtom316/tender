"""Assemble evidence pack tool — gathers all context needed for chapter generation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tender_backend.tools.base import BaseTool, ToolResult
from tender_backend.tools.registry import register_tool


class AssembleEvidencePackInput(BaseModel):
    project_id: str = Field(..., description="Project UUID")
    section_name: str = Field(..., description="Target section/chapter name")


class AssembleEvidencePackTool(BaseTool):
    name = "assemble_evidence_pack"
    description = "Gather project facts, requirements, scoring criteria, matched clauses, and reference sections for chapter generation"

    def get_input_schema(self) -> type[BaseModel]:
        return AssembleEvidencePackInput

    async def execute(self, params: BaseModel) -> ToolResult:
        p = params if isinstance(params, AssembleEvidencePackInput) else AssembleEvidencePackInput(**params.model_dump())
        from tender_backend.services.search_service.query_service import search_clauses, search_sections
        try:
            clauses = await search_clauses(p.section_name, top_k=10)
            sections = await search_sections(p.section_name, project_id=p.project_id, top_k=5)
            return ToolResult(
                success=True,
                data={
                    "project_id": p.project_id,
                    "section_name": p.section_name,
                    "matched_clauses": clauses,
                    "reference_sections": sections,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


register_tool(AssembleEvidencePackTool())
