"""Submission-preparation checklist generation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row


class SubmissionChecklistService:
    def build(self, conn: Connection, *, project_id: UUID) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            project = cur.execute("SELECT * FROM project WHERE id = %s", (project_id,)).fetchone()
            requirements = cur.execute(
                """
                SELECT id, category, title, requirement_text, source_text, human_confirmed
                FROM project_requirement
                WHERE project_id = %s
                ORDER BY category, created_at
                """,
                (project_id,),
            ).fetchall()
            attachments = cur.execute(
                "SELECT * FROM external_bid_attachment WHERE project_id = %s ORDER BY created_at",
                (project_id,),
            ).fetchall()
        project = dict(project or {})
        signature_items = []
        copy_items = []
        platform_items = []
        bond_items = []
        for row in requirements:
            text = " ".join(str(row.get(key) or "") for key in ["title", "requirement_text", "source_text"])
            item = {"requirement_id": str(row["id"]), "title": row["title"], "confirmed": row["human_confirmed"]}
            if any(word in text for word in ["签章", "盖章", "签字", "CA", "电子签名"]):
                signature_items.append(item)
            if any(word in text for word in ["正本", "副本", "份数", "密封", "电子版"]):
                copy_items.append(item)
            if any(word in text for word in ["上传", "文件大小", "命名", "平台"]):
                platform_items.append(item)
            if any(word in text for word in ["保证金", "保函", "投标担保"]):
                bond_items.append(item)
        return {
            "project_id": str(project_id),
            "deadline": project.get("submission_deadline"),
            "bid_opening_time": project.get("bid_opening_time"),
            "bid_bond_deadline": project.get("bid_bond_deadline"),
            "submission_target": project.get("submission_target") or "local_zip",
            "tender_platform": project.get("tender_platform"),
            "platform_file_rules": project.get("platform_file_rules") or {},
            "file_list": [
                {"name": "投标文件.docx", "required": True},
                {"name": "投标文件.pdf", "required": True},
                *[
                    {"name": row["filename"], "required": False, "type": row["attachment_type"]}
                    for row in attachments
                ],
            ],
            "signature_items": signature_items,
            "copy_items": copy_items,
            "platform_items": platform_items,
            "bond_items": bond_items,
            "external_attachments": [dict(row) for row in attachments],
        }


__all__ = ["SubmissionChecklistService"]
