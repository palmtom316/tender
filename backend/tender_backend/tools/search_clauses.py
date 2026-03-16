"""Search clauses tool — searches standard clauses in OpenSearch."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tender_backend.tools.base import BaseTool, ToolResult
from tender_backend.tools.registry import register_tool


class SearchClausesInput(BaseModel):
    query: str = Field(..., description="Search query text")
    specialty: str | None = Field(None, description="Filter by specialty (e.g., 土建, 安装)")
    top_k: int = Field(5, description="Number of results to return")


class SearchClausesTool(BaseTool):
    name = "search_clauses"
    description = "Search standard clauses by keyword with Chinese synonym expansion"

    def get_input_schema(self) -> type[BaseModel]:
        return SearchClausesInput

    async def execute(self, params: BaseModel) -> ToolResult:
        p = params if isinstance(params, SearchClausesInput) else SearchClausesInput(**params.model_dump())
        from tender_backend.services.search_service.query_service import search_clauses
        try:
            results = await search_clauses(
                query=p.query,
                specialty=p.specialty,
                top_k=p.top_k,
            )
            return ToolResult(success=True, data={"clauses": results})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


register_tool(SearchClausesTool())
