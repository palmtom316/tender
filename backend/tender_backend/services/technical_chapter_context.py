"""Build traceable inputs for technical chapter drafting."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.services.technical_chapter_strategies import (
    SITE_CONDITION_KEYWORDS,
    chart_recommendations_for_chapter,
    prompt_template_for_chapter,
    strategy_for_chapter,
)
from tender_backend.services.tender_constraint_service import TenderConstraintService


class TechnicalChapterContextBuilder:
    def build(self, conn: Connection, *, project_id: UUID, chapter_id: UUID) -> dict[str, Any]:
        chapter = self._chapter(conn, project_id=project_id, chapter_id=chapter_id)
        if chapter is None:
            raise ValueError("technical chapter not found")
        constraint_set = TenderConstraintService().latest_confirmed(conn, project_id=project_id)
        constraints = self._constraints_for_chapter(constraint_set, chapter_code=chapter["chapter_code"])
        requirement_ids = [item["requirement_id"] for item in constraints if item.get("requirement_id")]
        strategy = strategy_for_chapter(chapter.get("chapter_code"))
        tender_summary = self._tender_summary(conn, project_id=project_id)
        return {
            "project_id": str(project_id),
            "chapter": chapter,
            "constraint_set": _compact_constraint_set(constraint_set),
            "constraints": constraints,
            "tender_summary": tender_summary,
            "matched_keywords": _matched_site_condition_keywords(tender_summary),
            "scoring_items": self._scoring_items(conn, project_id=project_id, chapter=chapter),
            "standard_clauses": self._standard_clauses(conn, requirement_ids=requirement_ids),
            "personnel_selections": self._personnel_selections(conn, project_id=project_id),
            "equipment_selections": self._equipment_selections(conn, project_id=project_id),
            "company_assets": self._company_assets(conn),
            "chart_assets": self._chart_assets(conn, project_id=project_id, chapter_id=chapter_id),
            "recommended_charts": chart_recommendations_for_chapter(chapter.get("chapter_code")),
            "strategy": _strategy_to_dict(strategy),
            "prompt_template": prompt_template_for_chapter(chapter.get("chapter_code")),
            "trace_policy": {
                "source_trace_visibility": "metadata_and_review_panel",
                "standard_source_policy": "local_library_only",
            },
        }

    def _chapter(self, conn: Connection, *, project_id: UUID, chapter_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM bid_chapter WHERE id = %s AND project_id = %s",
                (chapter_id, project_id),
            ).fetchone()
        return dict(row) if row else None

    def _constraints_for_chapter(self, constraint_set: dict[str, Any] | None, *, chapter_code: str) -> list[dict[str, Any]]:
        if not constraint_set:
            return []
        result: list[dict[str, Any]] = []
        for item in constraint_set.get("items") or []:
            metadata = item.get("metadata_json") or {}
            mapped_code = str(metadata.get("mapped_chapter_code") or metadata.get("chapter_code") or "")
            mapped_codes = [str(value) for value in metadata.get("mapped_chapter_codes") or []]
            if mapped_code and mapped_code != chapter_code and chapter_code not in mapped_codes:
                continue
            if not mapped_code and mapped_codes and chapter_code not in mapped_codes:
                continue
            result.append(
                {
                    "id": item.get("id"),
                    "requirement_id": item.get("requirement_id"),
                    "category": item.get("category"),
                    "constraint_subtype": item.get("constraint_subtype") or metadata.get("constraint_subtype"),
                    "title": item.get("title"),
                    "constraint_text": item.get("constraint_text") or "",
                    "source_file": item.get("source_file"),
                    "source_locator": item.get("source_locator"),
                    "metadata_json": metadata,
                }
            )
        return result

    def _tender_summary(self, conn: Connection, *, project_id: UUID) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT project_name, tenderer, tender_agency, project_location, construction_period,
                       quality_requirement, bid_open_time, bid_deadline, raw_facts_json
                FROM tender_summary
                WHERE project_id = %s
                """,
                (project_id,),
            ).fetchone()
        return dict(row) if row else {}

    def _scoring_items(self, conn: Connection, *, project_id: UUID, chapter: dict[str, Any]) -> list[dict[str, Any]]:
        needle = f"%{chapter.get('chapter_title') or chapter.get('chapter_code')}%"
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, dimension, max_score, scoring_method, source_file, source_locator, sub_items_json
                FROM scoring_criteria
                WHERE project_id = %s
                  AND (dimension ILIKE %s OR COALESCE(scoring_method, '') ILIKE %s)
                ORDER BY created_at
                """,
                (project_id, needle, needle),
            ).fetchall()
        return [dict(row) for row in rows]

    def _standard_clauses(self, conn: Connection, *, requirement_ids: list[UUID]) -> list[dict[str, Any]]:
        if not requirement_ids:
            return []
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT rm.id, rm.requirement_id, rm.match_status, rm.matched_source_type,
                       rm.matched_source_id, rm.matched_title, rm.evidence_summary,
                       sc.clause_no, sc.clause_title, sc.clause_text, s.standard_name, s.standard_code
                FROM requirement_match rm
                LEFT JOIN standard_clause sc
                  ON sc.id = rm.matched_source_id
                 AND rm.matched_source_type = 'standard_clause'
                LEFT JOIN standard s ON s.id = sc.standard_id
                WHERE rm.requirement_id = ANY(%s)
                  AND rm.match_status = 'matched'
                ORDER BY rm.created_at
                """,
                (requirement_ids,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _personnel_selections(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, intended_role, snapshot_json, confirmed, display_order
                FROM project_personnel_selection
                WHERE project_id = %s
                ORDER BY display_order, created_at
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _equipment_selections(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, asset_type, intended_role, snapshot_json, confirmed, display_order
                FROM project_equipment_selection
                WHERE project_id = %s
                ORDER BY asset_type, display_order, created_at
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _company_assets(self, conn: Connection) -> dict[str, list[dict[str, Any]]]:
        return {
            "company_profiles": self._company_profiles(conn),
            "certificates": self._certificates(conn),
            "performances": self._performances(conn),
            "evidence_assets": self._evidence_assets(conn),
            "method_statements": self._method_statements(conn),
        }

    def _company_profiles(self, conn: Connection) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, company_name, business_scope, profile_json
                FROM company_profile
                ORDER BY created_at DESC
                LIMIT 3
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def _certificates(self, conn: Connection) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, certificate_name, grade, specialty, valid_to, status
                FROM qualification_certificate
                WHERE COALESCE(status, 'active') = 'active'
                ORDER BY valid_to DESC NULLS LAST, created_at DESC
                LIMIT 12
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def _performances(self, conn: Connection) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, project_name, client_name, service_scope, evidence_summary
                FROM project_performance
                ORDER BY started_on DESC NULLS LAST, created_at DESC
                LIMIT 8
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def _evidence_assets(self, conn: Connection) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, asset_name, asset_domain, asset_type, file_name
                FROM evidence_asset
                ORDER BY owner_type, sort_order, created_at DESC
                LIMIT 20
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def _method_statements(self, conn: Connection) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, asset_name, asset_domain, asset_type, file_name, metadata_json
                FROM evidence_asset
                WHERE asset_domain IN ('method_statement', 'technical_method', 'construction_method')
                   OR asset_type IN ('method_statement', 'technical_method')
                ORDER BY sort_order, created_at DESC
                LIMIT 8
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def _chart_assets(self, conn: Connection, *, project_id: UUID, chapter_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, chart_type, placeholder_key, title, status, metadata_json
                FROM chart_asset
                WHERE project_id = %s
                  AND (outline_node_id = %s OR outline_node_id IS NULL)
                ORDER BY chart_type, created_at DESC
                """,
                (project_id, chapter_id),
            ).fetchall()
        return [dict(row) for row in rows]


def _compact_constraint_set(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {
        "id": value.get("id"),
        "version": value.get("version"),
        "status": value.get("status"),
        "metadata_json": value.get("metadata_json") or {},
    }


def _strategy_to_dict(strategy: Any) -> dict[str, Any]:
    if strategy is None:
        return {}
    return {
        "key": strategy.key,
        "purpose": strategy.purpose,
        "sections": [{"heading": heading, "body": body} for heading, body in strategy.sections],
        "required_facts": list(strategy.required_facts),
        "required_standards": list(strategy.required_standards),
        "required_charts": list(strategy.required_charts),
        "innovation_slots": list(strategy.innovation_slots),
        "self_check_rules": list(strategy.self_check_rules),
        "forbidden_terms": list(strategy.forbidden_terms),
        "prompt_template_path": strategy.prompt_template_path,
    }


def _matched_site_condition_keywords(tender_summary: dict[str, Any]) -> list[str]:
    if not tender_summary:
        return []
    source_text = " ".join(
        [
            str(tender_summary.get("project_location") or ""),
            _flatten_text(tender_summary.get("raw_facts_json") or {}),
        ]
    )
    return [keyword for keyword in SITE_CONDITION_KEYWORDS if keyword in source_text]


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    if value is None:
        return ""
    return str(value)


__all__ = ["TechnicalChapterContextBuilder"]
