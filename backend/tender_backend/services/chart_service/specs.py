from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


SUPPORTED_CHART_TYPES = {
    "org_chart",
    "construction_flow",
    "schedule_gantt",
    "responsibility_matrix",
    "risk_matrix",
    "quality_system",
    "safety_system",
    "emergency_org",
}

FLOW_CHART_TYPES = {
    "org_chart",
    "construction_flow",
    "quality_system",
    "safety_system",
    "emergency_org",
}

_SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_PLACEHOLDER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_MARKUP_RE = re.compile(r"</?[A-Za-z][^>]*>|<script|</script|<style|</style", re.IGNORECASE)


class ChartValidationError(ValueError):
    def __init__(self, issues: list[dict[str, str]]):
        super().__init__("invalid chart spec")
        self.issues = issues


class ChartNode(BaseModel):
    id: str
    label: str = Field(min_length=1, max_length=80)
    parent: str | None = None

    @field_validator("id", "parent")
    @classmethod
    def safe_id(cls, value: str | None) -> str | None:
        if value is not None and not _SAFE_ID_RE.match(value):
            raise ValueError("must be a safe ASCII identifier")
        return value

    @field_validator("label")
    @classmethod
    def plain_label(cls, value: str) -> str:
        return _plain_text(value)


class ChartEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    label: str | None = Field(default=None, max_length=60)

    @field_validator("from_", "to")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not _SAFE_ID_RE.match(value):
            raise ValueError("must be a safe ASCII identifier")
        return value

    @field_validator("label")
    @classmethod
    def plain_label(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None


class FlowChartSpec(BaseModel):
    chart_type: Literal["org_chart", "construction_flow", "quality_system", "safety_system", "emergency_org"]
    title: str = Field(min_length=1, max_length=100)
    placeholder_key: str | None = None
    direction: Literal["TB", "TD", "BT", "LR", "RL"] = "TB"
    nodes: list[ChartNode] = Field(min_length=1, max_length=80)
    edges: list[ChartEdge] = Field(default_factory=list, max_length=120)
    caption_title: str | None = Field(default=None, max_length=100)
    figure_no: str | None = Field(default=None, max_length=30)

    @field_validator("title", "caption_title", "figure_no")
    @classmethod
    def plain_text(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None

    @field_validator("placeholder_key")
    @classmethod
    def safe_placeholder(cls, value: str | None) -> str | None:
        return _safe_placeholder(value)

    @model_validator(mode="after")
    def check_edges(self) -> FlowChartSpec:
        ids = {node.id for node in self.nodes}
        for edge in self.edges:
            if edge.from_ not in ids or edge.to not in ids:
                raise ValueError("edges must reference existing nodes")
        return self


class GanttTask(BaseModel):
    id: str
    label: str = Field(min_length=1, max_length=80)
    start: date
    end: date
    group: str | None = Field(default=None, max_length=60)

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not _SAFE_ID_RE.match(value):
            raise ValueError("must be a safe ASCII identifier")
        return value

    @field_validator("label", "group")
    @classmethod
    def plain_text(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None

    @model_validator(mode="after")
    def check_period(self) -> GanttTask:
        if self.end < self.start:
            raise ValueError("task end must not be before start")
        return self


class GanttDependency(BaseModel):
    from_: str = Field(alias="from")
    to: str

    @field_validator("from_", "to")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not _SAFE_ID_RE.match(value):
            raise ValueError("must be a safe ASCII identifier")
        return value


class GanttChartSpec(BaseModel):
    chart_type: Literal["schedule_gantt"]
    title: str = Field(min_length=1, max_length=100)
    placeholder_key: str | None = None
    date_format: Literal["YYYY-MM-DD"] = "YYYY-MM-DD"
    tasks: list[GanttTask] = Field(min_length=1, max_length=80)
    dependencies: list[GanttDependency] = Field(default_factory=list, max_length=120)
    caption_title: str | None = Field(default=None, max_length=100)
    figure_no: str | None = Field(default=None, max_length=30)

    @field_validator("title", "caption_title", "figure_no")
    @classmethod
    def plain_text(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None

    @field_validator("placeholder_key")
    @classmethod
    def safe_placeholder(cls, value: str | None) -> str | None:
        return _safe_placeholder(value)

    @model_validator(mode="after")
    def check_dependencies(self) -> GanttChartSpec:
        ids = {task.id for task in self.tasks}
        for dependency in self.dependencies:
            if dependency.from_ not in ids or dependency.to not in ids:
                raise ValueError("dependencies must reference existing tasks")
        return self


class RiskCell(BaseModel):
    row: str = Field(min_length=1, max_length=40)
    column: str = Field(min_length=1, max_length=40)
    items: list[str] = Field(default_factory=list, max_length=8)
    level: Literal["low", "medium", "high", "critical"] | None = None
    color: str | None = Field(default=None, max_length=20)

    @field_validator("row", "column", "level", "color")
    @classmethod
    def plain_text(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None

    @field_validator("items")
    @classmethod
    def plain_items(cls, values: list[str]) -> list[str]:
        return [_plain_text(value) for value in values if _plain_text(value)]


class RiskMatrixSpec(BaseModel):
    chart_type: Literal["risk_matrix"]
    title: str = Field(min_length=1, max_length=100)
    placeholder_key: str | None = None
    rows: list[str] = Field(min_length=1, max_length=8)
    columns: list[str] = Field(min_length=1, max_length=8)
    cells: list[RiskCell] = Field(default_factory=list, max_length=64)
    caption_title: str | None = Field(default=None, max_length=100)
    figure_no: str | None = Field(default=None, max_length=30)

    @field_validator("title", "caption_title", "figure_no")
    @classmethod
    def plain_text(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None

    @field_validator("rows", "columns")
    @classmethod
    def plain_axis(cls, values: list[str]) -> list[str]:
        cleaned = [_plain_text(value) for value in values]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("axis labels must be unique")
        return cleaned

    @field_validator("placeholder_key")
    @classmethod
    def safe_placeholder(cls, value: str | None) -> str | None:
        return _safe_placeholder(value)

    @model_validator(mode="after")
    def check_cells(self) -> RiskMatrixSpec:
        rows = set(self.rows)
        columns = set(self.columns)
        for cell in self.cells:
            if cell.row not in rows or cell.column not in columns:
                raise ValueError("cells must reference existing rows and columns")
        return self


class ResponsibilityAssignment(BaseModel):
    role: str = Field(min_length=1, max_length=50)
    activity: str = Field(min_length=1, max_length=80)
    level: str = Field(min_length=1, max_length=20)

    @field_validator("role", "activity", "level")
    @classmethod
    def plain_text(cls, value: str) -> str:
        return _plain_text(value)


class ResponsibilityMatrixSpec(BaseModel):
    chart_type: Literal["responsibility_matrix"]
    title: str = Field(min_length=1, max_length=100)
    placeholder_key: str | None = None
    roles: list[str] = Field(min_length=1, max_length=12)
    activities: list[str] = Field(min_length=1, max_length=40)
    assignments: list[ResponsibilityAssignment] = Field(default_factory=list, max_length=160)
    caption_title: str | None = Field(default=None, max_length=100)
    figure_no: str | None = Field(default=None, max_length=30)

    @field_validator("title", "caption_title", "figure_no")
    @classmethod
    def plain_text(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None

    @field_validator("roles", "activities")
    @classmethod
    def plain_axis(cls, values: list[str]) -> list[str]:
        cleaned = [_plain_text(value) for value in values]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("labels must be unique")
        return cleaned

    @field_validator("placeholder_key")
    @classmethod
    def safe_placeholder(cls, value: str | None) -> str | None:
        return _safe_placeholder(value)

    @model_validator(mode="after")
    def check_assignments(self) -> ResponsibilityMatrixSpec:
        roles = set(self.roles)
        activities = set(self.activities)
        for assignment in self.assignments:
            if assignment.role not in roles or assignment.activity not in activities:
                raise ValueError("assignments must reference existing roles and activities")
        return self


ChartSpec = FlowChartSpec | GanttChartSpec | RiskMatrixSpec | ResponsibilityMatrixSpec


def parse_chart_spec(spec_json: dict[str, Any]) -> ChartSpec:
    chart_type = str(spec_json.get("chart_type") or "")
    try:
        if chart_type in FLOW_CHART_TYPES:
            return FlowChartSpec.model_validate(spec_json)
        if chart_type == "schedule_gantt":
            return GanttChartSpec.model_validate(spec_json)
        if chart_type == "risk_matrix":
            return RiskMatrixSpec.model_validate(spec_json)
        if chart_type == "responsibility_matrix":
            return ResponsibilityMatrixSpec.model_validate(spec_json)
    except ValidationError as exc:
        raise ChartValidationError(_validation_issues(exc)) from exc
    raise ChartValidationError([{"code": "unsupported_chart_type", "message": f"unsupported chart type: {chart_type}"}])


def validate_chart_spec(spec_json: dict[str, Any]) -> dict[str, Any]:
    try:
        spec = parse_chart_spec(spec_json)
    except ChartValidationError as exc:
        return {"valid": False, "issues": exc.issues}
    return {"valid": True, "issues": [], "normalized_spec": spec.model_dump(by_alias=True, mode="json")}


def _plain_text(value: str) -> str:
    cleaned = " ".join(str(value).split())
    if _MARKUP_RE.search(cleaned):
        raise ValueError("markup is not allowed")
    return cleaned


def _safe_placeholder(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not _PLACEHOLDER_RE.match(cleaned):
        raise ValueError("placeholder_key must be a safe identifier")
    return cleaned


def _validation_issues(exc: ValidationError) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        code = str(error.get("type") or "invalid")
        message = str(error.get("msg") or "invalid value")
        issues.append({"code": code, "message": f"{loc}: {message}" if loc else message})
    return issues
