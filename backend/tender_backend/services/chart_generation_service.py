"""Structured chart asset creation and simple SVG rendering."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


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


class ChartGenerationService:
    def create_or_update(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        chart_type: str,
        title: str,
        spec_json: dict[str, Any],
        outline_node_id: UUID | None = None,
    ) -> dict[str, Any]:
        if chart_type not in SUPPORTED_CHART_TYPES:
            raise ValueError(f"unsupported chart type: {chart_type}")
        validation = self.validate(chart_type=chart_type, spec_json=spec_json)
        status = "draft" if validation["valid"] else "needs_review"
        svg = self.render_svg(title=title, spec_json=spec_json)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO chart_asset (
                  id, project_id, outline_node_id, chart_type, title, spec_json, rendered_svg, status, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), project_id, outline_node_id, chart_type, title, Jsonb(spec_json), svg, status, Jsonb({"validation": validation})),
            ).fetchone()
        conn.commit()
        return dict(row) if row else {}

    def list_by_project(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM chart_asset WHERE project_id = %s ORDER BY chart_type, created_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def validate(self, *, chart_type: str, spec_json: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        if chart_type in {"org_chart", "emergency_org"} and not spec_json.get("nodes"):
            issues.append({"code": "missing_nodes", "message": "组织类图表至少需要 nodes。"})
        if chart_type in {"construction_flow", "quality_system", "safety_system"} and not (
            spec_json.get("steps") or spec_json.get("nodes")
        ):
            issues.append({"code": "missing_steps", "message": "流程类图表至少需要 steps 或 nodes。"})
        return {"valid": not issues, "issues": issues}

    def render_svg(self, *, title: str, spec_json: dict[str, Any]) -> str:
        labels = [_label(item) for item in spec_json.get("nodes") or spec_json.get("steps") or []]
        if not labels:
            labels = ["待补充"]
        height = 80 + len(labels) * 44
        rows = []
        for index, label in enumerate(labels):
            y = 58 + index * 44
            rows.append(f"<rect x='24' y='{y}' width='420' height='28' rx='6' fill='#eef2e6' stroke='#9aaa7a'/>")
            rows.append(f"<text x='38' y='{y + 19}' font-size='14' fill='#24301f'>{_escape(label)}</text>")
        return (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='480' height='{height}' viewBox='0 0 480 {height}'>"
            "<rect width='480' height='100%' fill='#fbfaf4'/>"
            f"<text x='24' y='32' font-size='18' font-weight='700' fill='#24301f'>{_escape(title)}</text>"
            f"{''.join(rows)}"
            "</svg>"
        )


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _label(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("label") or item.get("name") or item)
    return str(item)


__all__ = ["ChartGenerationService", "SUPPORTED_CHART_TYPES"]
