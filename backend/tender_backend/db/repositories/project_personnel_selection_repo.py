from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class ProjectPersonnelSelectionRow:
    id: UUID
    project_id: UUID
    person_id: UUID
    intended_role: str | None
    snapshot_json: dict[str, Any] | None
    display_order: int
    confirmed: bool
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


_SELECTION_COLUMNS = (
    "id, project_id, person_id, intended_role, snapshot_json, display_order, "
    "confirmed, confirmed_at, created_at, updated_at"
)


def _to_selection(row: dict[str, Any]) -> ProjectPersonnelSelectionRow:
    return ProjectPersonnelSelectionRow(
        id=row["id"],
        project_id=row["project_id"],
        person_id=row["person_id"],
        intended_role=row["intended_role"],
        snapshot_json=dict(row["snapshot_json"] or {}) if row["snapshot_json"] is not None else None,
        display_order=row["display_order"],
        confirmed=row["confirmed"],
        confirmed_at=row["confirmed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProjectPersonnelSelectionRepository:
    def list_people(
        self,
        conn: Connection,
        *,
        library_company_id: UUID | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        values: list[Any] = []
        if library_company_id is not None:
            clauses.append("library_company_id = %s")
            values.append(library_company_id)
        if q:
            needle = f"%{q.strip()}%"
            clauses.append(
                "("
                "full_name ILIKE %s OR COALESCE(role_name, '') ILIKE %s OR "
                "COALESCE(specialty, '') ILIKE %s OR COALESCE(title, '') ILIKE %s OR "
                "COALESCE(phone, '') ILIKE %s"
                ")"
            )
            values.extend([needle, needle, needle, needle, needle])
        where_sql = " AND ".join(clauses)
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT
                  id, library_company_id, full_name, gender, age, education, title,
                  role_name, specialty, years_experience, phone, email, resume_text,
                  profile_json, created_at, updated_at
                FROM person_profile
                WHERE {where_sql}
                ORDER BY role_name NULLS LAST, full_name, created_at DESC
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_selections(self, conn: Connection, *, project_id: UUID) -> list[ProjectPersonnelSelectionRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_SELECTION_COLUMNS}
                FROM project_personnel_selection
                WHERE project_id = %s
                ORDER BY display_order, created_at
                """,
                (project_id,),
            ).fetchall()
        return [_to_selection(row) for row in rows]

    def create_selection(self, conn: Connection, *, project_id: UUID, person_id: UUID) -> ProjectPersonnelSelectionRow:
        with conn.cursor(row_factory=dict_row) as cur:
            person = cur.execute(
                "SELECT role_name FROM person_profile WHERE id = %s",
                (person_id,),
            ).fetchone()
            if person is None:
                raise ValueError("person profile not found")
            existing = cur.execute(
                f"""
                SELECT {_SELECTION_COLUMNS}
                FROM project_personnel_selection
                WHERE project_id = %s AND person_id = %s
                """,
                (project_id, person_id),
            ).fetchone()
            if existing is not None:
                return _to_selection(existing)
            order_row = cur.execute(
                "SELECT COALESCE(MAX(display_order), 0) AS max_order FROM project_personnel_selection WHERE project_id = %s",
                (project_id,),
            ).fetchone()
            row = cur.execute(
                f"""
                INSERT INTO project_personnel_selection (
                  id, project_id, person_id, intended_role, display_order
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (project_id, person_id) DO UPDATE
                SET updated_at = project_personnel_selection.updated_at
                RETURNING {_SELECTION_COLUMNS}
                """,
                (
                    uuid4(),
                    project_id,
                    person_id,
                    person["role_name"],
                    int(order_row["max_order"] or 0) + 1,
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_selection(row)

    def update_selection(self, conn: Connection, record_id: UUID, **fields: Any) -> ProjectPersonnelSelectionRow | None:
        sets: list[str] = []
        values: list[Any] = []
        for key in ("intended_role", "display_order"):
            if key in fields:
                sets.append(f"{key} = %s")
                values.append(fields[key])
        if "snapshot_json" in fields:
            sets.append("snapshot_json = %s::jsonb")
            values.append(json.dumps(fields["snapshot_json"] or {}, ensure_ascii=False))
        if "confirmed" in fields:
            sets.append("confirmed = %s")
            values.append(fields["confirmed"])
        if "confirmed_at" in fields:
            sets.append("confirmed_at = %s")
            values.append(fields["confirmed_at"])
        if not sets:
            return self.get_selection(conn, record_id)
        sets.append("updated_at = now()")
        values.append(record_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE project_personnel_selection
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING {_SELECTION_COLUMNS}
                """,
                values,
            ).fetchone()
        conn.commit()
        return _to_selection(row) if row else None

    def get_selection(self, conn: Connection, record_id: UUID) -> ProjectPersonnelSelectionRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_SELECTION_COLUMNS} FROM project_personnel_selection WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_selection(row) if row else None

    def delete_selection(self, conn: Connection, record_id: UUID) -> bool:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM project_personnel_selection WHERE id = %s", (record_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted

    def confirm_project_selections(self, conn: Connection, *, project_id: UUID) -> list[ProjectPersonnelSelectionRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT
                  pps.id AS selection_id,
                  pps.intended_role,
                  pp.id AS person_id,
                  pp.library_company_id,
                  pp.full_name,
                  pp.gender,
                  pp.age,
                  pp.education,
                  pp.title,
                  pp.role_name,
                  pp.specialty,
                  pp.years_experience,
                  pp.phone,
                  pp.email,
                  pp.resume_text,
                  pp.profile_json
                FROM project_personnel_selection pps
                JOIN person_profile pp ON pp.id = pps.person_id
                WHERE pps.project_id = %s
                ORDER BY pps.display_order, pps.created_at
                """,
                (project_id,),
            ).fetchall()
            selection_ids: list[UUID] = []
            person_ids = [row["person_id"] for row in rows]
            attachments_by_person = self._load_person_attachments(cur, person_ids)
            for row in rows:
                snapshot = {
                    "person_id": str(row["person_id"]),
                    "library_company_id": str(row["library_company_id"]) if row["library_company_id"] else None,
                    "full_name": row["full_name"],
                    "gender": row["gender"],
                    "age": row["age"],
                    "education": row["education"],
                    "title": row["title"],
                    "role_name": row["role_name"],
                    "intended_role": row["intended_role"] or row["role_name"],
                    "specialty": row["specialty"],
                    "years_experience": row["years_experience"],
                    "phone": row["phone"],
                    "email": row["email"],
                    "resume_text": row["resume_text"],
                    "profile_json": dict(row["profile_json"] or {}),
                    "attachments": attachments_by_person.get(row["person_id"], []),
                }
                cur.execute(
                    """
                    UPDATE project_personnel_selection
                    SET snapshot_json = %s::jsonb,
                        confirmed = TRUE,
                        confirmed_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps(snapshot, ensure_ascii=False, default=str), row["selection_id"]),
                )
                selection_ids.append(row["selection_id"])
            if not selection_ids:
                conn.commit()
                return []
            confirmed_rows = cur.execute(
                f"""
                SELECT {_SELECTION_COLUMNS}
                FROM project_personnel_selection
                WHERE id = ANY(%s)
                ORDER BY display_order, created_at
                """,
                (selection_ids,),
            ).fetchall()
        conn.commit()
        return [_to_selection(row) for row in confirmed_rows]

    def _load_person_attachments(self, cur, person_ids: list[UUID]) -> dict[UUID, list[dict[str, Any]]]:
        if not person_ids:
            return {}
        rows = cur.execute(
            """
            SELECT owner_id, asset_name, asset_category, file_name, issuer_name, issued_on, expires_on, metadata_json
            FROM evidence_asset
            WHERE owner_type = 'person_profile'
              AND asset_domain = 'personnel'
              AND owner_id = ANY(%s)
            ORDER BY owner_id, sort_order, created_at DESC
            """,
            (person_ids,),
        ).fetchall()
        result: dict[UUID, list[dict[str, Any]]] = {}
        for row in rows:
            owner_id = row["owner_id"]
            result.setdefault(owner_id, []).append(
                {
                    "asset_name": row["asset_name"],
                    "asset_category": row["asset_category"],
                    "file_name": row["file_name"],
                    "issuer_name": row["issuer_name"],
                    "issued_on": row["issued_on"].isoformat() if row["issued_on"] else None,
                    "expires_on": row["expires_on"].isoformat() if row["expires_on"] else None,
                    "metadata_json": dict(row["metadata_json"] or {}),
                }
            )
        return result
