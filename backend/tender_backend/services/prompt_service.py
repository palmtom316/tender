"""Prompt service — manages versioned prompt templates with trace association."""

from __future__ import annotations

from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row

import structlog

logger = structlog.stdlib.get_logger(__name__)


class PromptService:
    def create_template(
        self,
        conn: Connection,
        *,
        prompt_name: str,
        template_text: str,
        variables: list[str] | None = None,
        description: str | None = None,
    ) -> dict:
        """Create a new version of a prompt template."""
        import json
        # Auto-increment version
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_ver FROM prompt_template WHERE prompt_name = %s",
                (prompt_name,),
            ).fetchone()
            next_version = row["next_ver"] if row else 1

            result = cur.execute(
                """
                INSERT INTO prompt_template (id, prompt_name, version, template_text, variables, description)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), prompt_name, next_version, template_text,
                 json.dumps(variables or []), description),
            ).fetchone()
        conn.commit()
        logger.info("prompt_created", name=prompt_name, version=next_version)
        return result  # type: ignore[return-value]

    def get_active_template(
        self, conn: Connection, *, prompt_name: str
    ) -> dict | None:
        """Get the latest active version of a prompt template."""
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT * FROM prompt_template
                WHERE prompt_name = %s AND active = TRUE
                ORDER BY version DESC LIMIT 1
                """,
                (prompt_name,),
            ).fetchone()
        return row

    def get_template_by_version(
        self, conn: Connection, *, prompt_name: str, version: int
    ) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM prompt_template WHERE prompt_name = %s AND version = %s",
                (prompt_name, version),
            ).fetchone()
        return row

    def list_versions(
        self, conn: Connection, *, prompt_name: str
    ) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT id, prompt_name, version, description, active, created_at FROM prompt_template WHERE prompt_name = %s ORDER BY version DESC",
                (prompt_name,),
            ).fetchall()

    def render(self, template_text: str, **kwargs: str) -> str:
        """Render a prompt template with provided variables."""
        result = template_text
        for key, value in kwargs.items():
            result = result.replace(f"{{{{{key}}}}}", value)
        return result
