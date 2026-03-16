"""Search sections tool — searches document sections in OpenSearch."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tender_backend.tools.base import BaseTool, ToolResult
from tender_backend.tools.registry import register_tool


class SearchSectionsInput(BaseModel):
    query: str = Field(..., description="Search query text")
    project_id: str | None = Field(None, description="Filter by project ID")
    top_k: int = Field(5, description="Number of results to return")


class SearchSectionsTool(BaseTool):
    name = "search_sections"
    description = "Search document sections by keyword with Chinese synonym expansion"

    def get_input_schema(self) -> type[BaseModel]:
        return SearchSectionsInput

    async def execute(self, params: BaseModel) -> ToolResult:
        p = params if isinstance(params, SearchSectionsInput) else SearchSectionsInput(**params.model_dump())
        from tender_backend.services.search_service.query_service import search_sections
        try:
            results = await search_sections(
                query=p.query,
                project_id=p.project_id,
                top_k=p.top_k,
            )
            return ToolResult(success=True, data={"sections": results})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


register_tool(SearchSectionsTool())
