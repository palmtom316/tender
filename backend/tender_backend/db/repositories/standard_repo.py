"""Repository for standard and standard_clause tables."""

from __future__ import annotations

import json as _json
import re
from collections import defaultdict
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.services.norm_service.document_assets import (
    build_document_asset,
    serialize_document_asset,
)


def _order_clauses_for_insert(clauses: list[dict]) -> list[dict]:
    """Insert self-referential clauses in dependency order.

    `standard_clause` has self-references on both `parent_id` and
    `commentary_clause_id`, so a child or commentary row may need another row
    from the same batch to exist first.
    """
    if len(clauses) < 2:
        return clauses

    clauses_by_id = {clause["id"]: clause for clause in clauses}
    original_index = {clause["id"]: index for index, clause in enumerate(clauses)}
    pending_deps: dict[UUID, set[UUID]] = {}
    dependents: dict[UUID, list[UUID]] = defaultdict(list)

    for clause in clauses:
        clause_id = clause["id"]
        deps: set[UUID] = set()
        for field in ("parent_id", "commentary_clause_id"):
            dep_id = clause.get(field)
            if dep_id and dep_id in clauses_by_id and dep_id != clause_id:
                deps.add(dep_id)
                dependents[dep_id].append(clause_id)
        pending_deps[clause_id] = deps

    ordered_ids: list[UUID] = []
    ready = [
        clause["id"]
        for clause in clauses
        if not pending_deps[clause["id"]]
    ]

    while ready:
        ready.sort(key=original_index.__getitem__)
        current_id = ready.pop(0)
        ordered_ids.append(current_id)
        for dependent_id in dependents.get(current_id, []):
            deps = pending_deps[dependent_id]
            deps.discard(current_id)
            if not deps and dependent_id not in ordered_ids and dependent_id not in ready:
                ready.append(dependent_id)

    if len(ordered_ids) != len(clauses):
        return clauses

    return [clauses_by_id[clause_id] for clause_id in ordered_ids]


_TOC_PAGE_REF = re.compile(r"(?:\(\d+\)|（\d+）)\s*$")
_TOC_DOT_LEADERS = re.compile(r"[.…]{2,}")


def _build_clause_node(clause: dict) -> dict:
    return {
        "id": str(clause["id"]),
        "clause_no": clause.get("clause_no"),
        "clause_title": clause.get("clause_title"),
        "clause_text": clause.get("clause_text"),
        "summary": clause.get("summary"),
        "tags": clause.get("tags", []),
        "clause_type": clause.get("clause_type") or "normative",
        "node_type": clause.get("node_type") or "clause",
        "node_key": clause.get("node_key"),
        "node_label": clause.get("node_label"),
        "page_start": clause.get("page_start"),
        "page_end": clause.get("page_end"),
        "sort_order": clause.get("sort_order"),
        "parent_id": str(clause["parent_id"]) if clause.get("parent_id") else None,
        "commentary_clause_id": (
            str(clause["commentary_clause_id"])
            if clause.get("commentary_clause_id")
            else None
        ),
        "source_type": clause.get("source_type", "text"),
        "source_label": clause.get("source_label"),
        "children": [],
    }


def _is_toc_section(section: dict) -> bool:
    title = (section.get("title") or "").strip()
    text = (section.get("text") or "").strip()
    if not title:
        return True
    if _TOC_PAGE_REF.search(title):
        return True
    if _TOC_DOT_LEADERS.search(title):
        return True
    if text and (
        _TOC_DOT_LEADERS.search(text)
        or sum(1 for line in text.splitlines() if _TOC_PAGE_REF.search(line.strip())) >= 2
    ):
        return True
    return False


def _find_outline_parent_by_code(outline_by_code: dict[str, dict], section_code: str | None) -> dict | None:
    if not section_code or "." not in section_code:
        return None
    parts = section_code.split(".")
    for size in range(len(parts) - 1, 0, -1):
        parent = outline_by_code.get(".".join(parts[:size]))
        if parent is not None:
            return parent
    return None


def _build_outline_tree(sections: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    filtered = [section for section in sections if not _is_toc_section(section)]
    if not filtered:
        return [], {}

    roots: list[dict] = []
    outline_by_code: dict[str, dict] = {}
    stack: list[dict] = []

    for index, section in enumerate(filtered):
        section_code = str(section.get("section_code") or "").strip() or None
        level = int(section.get("level") or 1)
        node = {
            "id": f"outline:{section['id']}",
            "clause_no": section_code,
            "clause_title": (section.get("title") or "").strip() or None,
            "clause_text": (section.get("text") or "").strip() or None,
            "summary": None,
            "tags": [],
            "clause_type": "outline",
            "node_type": "outline",
            "node_key": section_code or f"outline:{section['id']}",
            "node_label": None,
            "page_start": section.get("page_start"),
            "page_end": section.get("page_end") or section.get("page_start"),
            "sort_order": index,
            "parent_id": None,
            "commentary_clause_id": None,
            "children": [],
            "_level": level,
        }

        while stack and stack[-1]["_level"] >= level:
            stack.pop()

        parent = _find_outline_parent_by_code(outline_by_code, section_code)
        if parent is None and stack:
            parent = stack[-1]

        if parent is not None:
            node["parent_id"] = parent["id"]
            parent["children"].append(node)
        else:
            roots.append(node)

        stack.append(node)
        if section_code and section_code not in outline_by_code:
            outline_by_code[section_code] = node

    for node in outline_by_code.values():
        node.pop("_level", None)
    for node in roots:
        node.pop("_level", None)
        for child in node["children"]:
            _clear_outline_levels(child)

    return roots, outline_by_code


def _clear_outline_levels(node: dict) -> None:
    node.pop("_level", None)
    for child in node["children"]:
        _clear_outline_levels(child)


def _prune_outline_noise(nodes: list[dict]) -> list[dict]:
    pruned: list[dict] = []
    for node in nodes:
        children = _prune_outline_noise(node["children"])
        node["children"] = children
        if node.get("clause_type") != "outline" or children:
            pruned.append(node)
    return pruned


def _find_outline_host(outline_by_code: dict[str, dict], clause_no: str | None) -> dict | None:
    if not clause_no:
        return None
    return _find_outline_parent_by_code(outline_by_code, clause_no)


def _merge_clause_into_outline_node(target: dict, clause: dict) -> None:
    target["id"] = str(clause["id"])
    target["summary"] = clause.get("summary")
    target["tags"] = clause.get("tags", [])
    target["clause_type"] = clause.get("clause_type") or "normative"
    target["node_key"] = clause.get("node_key") or target.get("node_key")
    target["page_start"] = clause.get("page_start") or target.get("page_start")
    target["page_end"] = clause.get("page_end") or target.get("page_end")
    target["sort_order"] = clause.get("sort_order")
    target["commentary_clause_id"] = (
        str(clause["commentary_clause_id"])
        if clause.get("commentary_clause_id")
        else None
    )
    if clause.get("clause_text"):
        target["clause_text"] = clause["clause_text"]
    if not target.get("clause_title") and clause.get("clause_title"):
        target["clause_title"] = clause["clause_title"]


class StandardRepository:
    # ── Read helpers ──

    def get_standard(self, conn: Connection, standard_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT s.*, j.ocr_status, j.ai_status
                FROM standard s
                LEFT JOIN standard_processing_job j ON j.standard_id = s.id
                WHERE s.id = %s
                """,
                (standard_id,),
            ).fetchone()

    def get_standard_file(self, conn: Connection, standard_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT
                  s.id AS standard_id,
                  d.id AS document_id,
                  pf.id AS project_file_id,
                  pf.filename,
                  pf.content_type,
                  pf.storage_key
                FROM standard s
                JOIN document d ON d.id = s.document_id
                JOIN project_file pf ON pf.id = d.project_file_id
                WHERE s.id = %s
                """,
                (standard_id,),
            ).fetchone()

    def get_clause(self, conn: Connection, clause_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT
                  sc.*,
                  s.standard_name,
                  s.specialty
                FROM standard_clause sc
                JOIN standard s ON s.id = sc.standard_id
                WHERE sc.id = %s
                """,
                (clause_id,),
            ).fetchone()

    def get_clauses_by_ids(self, conn: Connection, clause_ids: list[UUID]) -> dict[str, dict]:
        if not clause_ids:
            return {}

        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT
                  sc.*,
                  s.standard_name,
                  s.specialty
                FROM standard_clause sc
                JOIN standard s ON s.id = sc.standard_id
                WHERE sc.id = ANY(%s)
                """,
                (clause_ids,),
            ).fetchall()

        return {str(row["id"]): row for row in rows}

    def list_neighbor_clauses(
        self,
        conn: Connection,
        *,
        standard_id: UUID,
        sort_order: int,
        radius: int = 2,
    ) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT *
                FROM standard_clause
                WHERE standard_id = %s
                  AND sort_order BETWEEN %s AND %s
                ORDER BY sort_order
                """,
                (standard_id, sort_order - radius, sort_order + radius),
            ).fetchall()

    def get_clause_count(self, conn: Connection, standard_id: UUID) -> int:
        with conn.cursor() as cur:
            row = cur.execute(
                "SELECT count(*) FROM standard_clause WHERE standard_id = %s",
                (standard_id,),
            ).fetchone()
            return row[0] if row else 0

    def get_clause_tree(self, conn: Connection, standard_id: UUID) -> list[dict]:
        """Fetch clauses and rebuild nested children tree in Python."""
        flat = self.list_clauses(conn, standard_id=standard_id)
        if not flat:
            return []

        by_id: dict[str, dict] = {}
        for c in flat:
            node = _build_clause_node(c)
            by_id[str(c["id"])] = node

        roots: list[dict] = []
        for node in by_id.values():
            commentary_parent_id = node.get("commentary_clause_id")
            pid = node["parent_id"]
            if node["clause_type"] == "commentary" and commentary_parent_id and commentary_parent_id in by_id:
                by_id[commentary_parent_id]["children"].append(node)
                continue
            if pid and pid in by_id:
                by_id[pid]["children"].append(node)
                continue
            roots.append(node)

        return roots

    def list_document_sections(self, conn: Connection, *, document_id: UUID) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT id, section_code, title, level, text, raw_json, text_source, sort_order, page_start, page_end
                FROM document_section
                WHERE document_id = %s
                ORDER BY
                  CASE WHEN page_start IS NULL THEN 1 ELSE 0 END,
                  page_start,
                  sort_order,
                  level,
                  ctid
                """,
                (document_id,),
            ).fetchall()

    def list_document_tables(self, conn: Connection, *, document_id: UUID) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT id, section_id, page, page_start, page_end, table_title, table_html, raw_json
                FROM document_table
                WHERE document_id = %s
                ORDER BY
                  CASE WHEN page_start IS NULL THEN 1 ELSE 0 END,
                  page_start,
                  page,
                  created_at
                """,
                (document_id,),
            ).fetchall()

    def get_document_parse_info(self, conn: Connection, *, document_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT id, parser_name, parser_version, raw_payload
                FROM document
                WHERE id = %s
                """,
                (document_id,),
            ).fetchone()

    def get_standard_parse_assets(self, conn: Connection, *, standard_id: UUID) -> dict | None:
        file_meta = self.get_standard_file(conn, standard_id)
        if not file_meta:
            return None

        document_id = file_meta["document_id"]
        document = self.get_document_parse_info(conn, document_id=document_id)
        sections = self.list_document_sections(conn, document_id=document_id)
        tables = self.list_document_tables(conn, document_id=document_id)
        document_asset = build_document_asset(
            document_id=document_id,
            document=document,
            sections=sections,
            tables=tables,
        )

        return {
            "document": serialize_document_asset(document_asset),
            "sections": sections,
            "tables": tables,
        }

    def get_viewer_tree(self, conn: Connection, standard_id: UUID) -> list[dict]:
        file_meta = self.get_standard_file(conn, standard_id)
        document_id = file_meta.get("document_id") if file_meta else None
        sections = (
            self.list_document_sections(conn, document_id=document_id)
            if document_id is not None
            else []
        )
        outline_roots, outline_by_code = _build_outline_tree(sections)

        flat = self.list_clauses(conn, standard_id=standard_id)
        if not flat:
            return outline_roots
        if not outline_roots:
            return self.get_clause_tree(conn, standard_id)

        mounted_by_clause_id: dict[str, dict] = {}
        detached_roots: list[dict] = []

        for clause in flat:
            clause_id = str(clause["id"])
            node_type = clause.get("node_type") or "clause"
            clause_no = clause.get("clause_no")
            clause_type = clause.get("clause_type") or "normative"

            exact_outline = None
            if clause_type != "commentary" and node_type == "clause" and clause_no:
                exact_outline = outline_by_code.get(clause_no)

            if exact_outline is not None:
                _merge_clause_into_outline_node(exact_outline, clause)
                mounted_by_clause_id[clause_id] = exact_outline
                continue

            node = _build_clause_node(clause)
            mounted_by_clause_id[clause_id] = node

            commentary_parent_id = node.get("commentary_clause_id")
            parent_id = node.get("parent_id")
            outline_host = _find_outline_host(outline_by_code, clause_no)

            if clause_type != "commentary" and node_type == "clause" and outline_host is not None:
                outline_host["children"].append(node)
                continue

            if node["clause_type"] == "commentary" and commentary_parent_id and commentary_parent_id in mounted_by_clause_id:
                mounted_by_clause_id[commentary_parent_id]["children"].append(node)
                continue

            if parent_id and parent_id in mounted_by_clause_id:
                mounted_by_clause_id[parent_id]["children"].append(node)
                continue

            if outline_host is not None:
                outline_host["children"].append(node)
                continue

            detached_roots.append(node)

        return [*_prune_outline_noise(outline_roots), *detached_roots]

    # ── Write helpers ──

    def update_processing_status(
        self,
        conn: Connection,
        standard_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> None:
        ts_col = (
            "processing_started_at" if status == "processing"
            else "processing_finished_at" if status in ("completed", "failed")
            else None
        )
        if ts_col:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE standard SET processing_status = %s, error_message = %s, {ts_col} = now() WHERE id = %s",
                    (status, error_message, standard_id),
                )
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE standard SET processing_status = %s, error_message = %s WHERE id = %s",
                    (status, error_message, standard_id),
                )
        conn.commit()

    def bulk_create_clauses(self, conn: Connection, clauses: list[dict]) -> int:
        """Bulk insert clause dicts. Returns count inserted."""
        if not clauses:
            return 0
        clauses = _order_clauses_for_insert(clauses)
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO standard_clause
                       (id, standard_id, parent_id, clause_no, clause_title,
                        clause_text, summary, tags, page_start, page_end,
                        sort_order, clause_type, commentary_clause_id, source_type, source_label,
                        node_type, node_key, node_label)
                   VALUES (%(id)s, %(standard_id)s, %(parent_id)s, %(clause_no)s,
                           %(clause_title)s, %(clause_text)s, %(summary)s,
                           %(tags)s, %(page_start)s, %(page_end)s,
                           %(sort_order)s, %(clause_type)s, %(commentary_clause_id)s, %(source_type)s, %(source_label)s,
                           %(node_type)s, %(node_key)s, %(node_label)s)""",
                [
                    {
                        **c,
                        "tags": _json.dumps(c.get("tags") or []),
                        "commentary_clause_id": c.get("commentary_clause_id"),
                        "source_type": c.get("source_type", "text"),
                        "source_label": c.get("source_label"),
                        "node_type": c.get("node_type", "clause"),
                        "node_key": c.get("node_key"),
                        "node_label": c.get("node_label"),
                    }
                    for c in clauses
                ],
            )
        conn.commit()
        return len(clauses)

    def delete_clauses(self, conn: Connection, standard_id: UUID) -> int:
        """Delete all clauses for a standard (supports re-processing)."""
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM standard_clause WHERE standard_id = %s", (standard_id,)
            )
            count = cur.rowcount
        conn.commit()
        return count

    def delete_standard(self, conn: Connection, *, standard_id: UUID) -> int:
        file_meta = self.get_standard_file(conn, standard_id)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM standard WHERE id = %s", (standard_id,))
            deleted = cur.rowcount
            if deleted and file_meta and file_meta.get("project_file_id"):
                cur.execute(
                    "DELETE FROM project_file WHERE id = %s",
                    (file_meta["project_file_id"],),
                )
        conn.commit()
        return deleted

    # ── Original methods ──
    def create_standard(
        self,
        conn: Connection,
        *,
        standard_code: str,
        standard_name: str,
        version_year: str | None = None,
        specialty: str | None = None,
        document_id: UUID | None = None,
    ) -> dict:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO standard
                    (id, standard_code, standard_name, version_year, specialty, document_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), standard_code, standard_name, version_year, specialty, document_id),
            ).fetchone()
        conn.commit()
        return row  # type: ignore[return-value]

    def create_clause(
        self,
        conn: Connection,
        *,
        standard_id: UUID,
        clause_no: str | None = None,
        clause_title: str | None = None,
        clause_text: str,
        summary: str | None = None,
        tags: list[str] | None = None,
        parent_id: UUID | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
        sort_order: int = 0,
    ) -> dict:
        import json
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO standard_clause
                    (id, standard_id, parent_id, clause_no, clause_title,
                     clause_text, summary, tags, page_start, page_end, sort_order, source_type, source_label,
                     node_type, node_key, node_label)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(), standard_id, parent_id, clause_no, clause_title,
                    clause_text, summary, json.dumps(tags or []),
                    page_start, page_end, sort_order, "text", None, "clause", clause_no, None,
                ),
            ).fetchone()
        conn.commit()
        return row  # type: ignore[return-value]

    def list_standards(self, conn: Connection) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                """
                SELECT
                  s.*,
                  j.ocr_status,
                  j.ai_status,
                  CASE
                    WHEN pf.storage_key LIKE '/tmp/pytest-of-%'
                      OR pf.storage_key LIKE '%/pytest-of-%'
                    THEN TRUE
                    ELSE FALSE
                  END AS is_dev_artifact
                FROM standard s
                LEFT JOIN standard_processing_job j ON j.standard_id = s.id
                LEFT JOIN document d ON d.id = s.document_id
                LEFT JOIN project_file pf ON pf.id = d.project_file_id
                ORDER BY s.standard_code
                """
            ).fetchall()

    def list_clauses(
        self, conn: Connection, *, standard_id: UUID
    ) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT * FROM standard_clause WHERE standard_id = %s ORDER BY sort_order",
                (standard_id,),
            ).fetchall()
