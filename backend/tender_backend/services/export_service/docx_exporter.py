"""DOCX exporter — renders chapter drafts into a Word template using docxtpl."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import structlog
from psycopg import Connection
from psycopg.rows import dict_row

logger = structlog.stdlib.get_logger(__name__)

TEMPLATE_DIR = Path(os.environ.get("TEMPLATE_DIR", "templates"))


def render_docx(
    conn: Connection,
    *,
    project_id: UUID,
    template_name: str = "default_technical_bid.docx",
    output_path: Path | None = None,
) -> Path:
    """Render project drafts into a DOCX file using docxtpl.

    Template placeholders: {{SECTION_<chapter_code>}} or {{<chapter_code>}}
    """
    from docxtpl import DocxTemplate

    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    doc = DocxTemplate(str(template_path))

    # Load all chapter drafts
    with conn.cursor(row_factory=dict_row) as cur:
        drafts = cur.execute(
            "SELECT chapter_code, content_md FROM chapter_draft WHERE project_id = %s",
            (project_id,),
        ).fetchall()

    # Build context: both SECTION_xxx and xxx placeholders
    context: dict[str, str] = {}
    for d in drafts:
        code = d["chapter_code"]
        content = d["content_md"]
        context[f"SECTION_{code}"] = content
        context[code] = content

    # Load project facts as additional context
    with conn.cursor(row_factory=dict_row) as cur:
        facts = cur.execute(
            "SELECT fact_key, fact_value FROM project_fact WHERE project_id = %s",
            (project_id,),
        ).fetchall()
    for f in facts:
        context[f["fact_key"]] = f["fact_value"]

    doc.render(context)

    if output_path is None:
        output_path = Path(f"/tmp/tender_export_{project_id}.docx")
    doc.save(str(output_path))

    logger.info("docx_rendered", project_id=str(project_id), output=str(output_path))
    return output_path
