"""AST models for normalized clause extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

PageNumber = int | str | None


@dataclass(slots=True)
class ClauseASTNode:
    """In-memory normalized clause node used before persistence projection."""

    id: UUID
    standard_id: UUID
    parent_id: UUID | None
    clause_no: str | None
    node_type: str
    node_key: str
    node_label: str | None
    clause_title: str | None
    clause_text: str
    summary: str | None
    tags: list[str] = field(default_factory=list)
    page_start: PageNumber = None
    page_end: PageNumber = None
    clause_type: str = "normative"
    source_type: str = "text"
    source_label: str | None = None
    source_ref: str | None = None
    source_refs: list[str] = field(default_factory=list)
    children: list["ClauseASTNode"] = field(default_factory=list)
