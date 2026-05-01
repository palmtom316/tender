"""DOCX exporter — renders chapter drafts into a Word template using docxtpl."""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from uuid import UUID

import structlog
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.services.export_service.doc_converter import convert_docx_to_doc
from tender_backend.services.tender_requirement_priority import load_tender_requirement_overrides

logger = structlog.stdlib.get_logger(__name__)

TEMPLATE_DIR = Path(os.environ.get("TEMPLATE_DIR", "templates"))
EXPORT_ROOT = Path(os.environ.get("TENDER_EXPORT_ROOT", "/tmp/tender-exports"))

EXPORT_MODE_SINGLE_DOCX = "single_docx"
EXPORT_MODE_MULTI_DOCX_ZIP = "multi_docx_zip"
EXPORT_MODE_MULTI_DOC_ZIP = "multi_doc_zip"
EXPORT_MODES: tuple[str, ...] = (
    EXPORT_MODE_SINGLE_DOCX,
    EXPORT_MODE_MULTI_DOCX_ZIP,
    EXPORT_MODE_MULTI_DOC_ZIP,
)


def _add_markdown_content(document: Document, content: str) -> None:
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            document.add_heading(line[2:].strip(), level=1)
        elif line.startswith("## "):
            document.add_heading(line[3:].strip(), level=2)
        elif line.startswith("### "):
            document.add_heading(line[4:].strip(), level=3)
        elif line.startswith("- "):
            document.add_paragraph(line[2:].strip(), style="List Bullet")
        else:
            document.add_paragraph(line)


def _load_project_name(conn: Connection, project_id: UUID) -> str:
    with conn.cursor() as cur:
        row = cur.execute("SELECT name FROM project WHERE id = %s", (project_id,)).fetchone()
    return str(row[0]) if row and row[0] else str(project_id)


def _apply_basic_style(document: Document) -> None:
    style = document.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(10.5)
    for section in document.sections:
        section.top_margin = Pt(72)
        section.bottom_margin = Pt(72)
        section.left_margin = Pt(72)
        section.right_margin = Pt(72)
        section.header.paragraphs[0].text = "投标文件"
        footer = section.footer.paragraphs[0]
        footer.text = "第 "
        run = footer.add_run()
        fld_char_begin = OxmlElement("w:fldChar")
        fld_char_begin.set(qn("w:fldCharType"), "begin")
        instr_text = OxmlElement("w:instrText")
        instr_text.set(qn("xml:space"), "preserve")
        instr_text.text = "PAGE"
        fld_char_end = OxmlElement("w:fldChar")
        fld_char_end.set(qn("w:fldCharType"), "end")
        run._r.append(fld_char_begin)
        run._r.append(instr_text)
        run._r.append(fld_char_end)
        footer.add_run(" 页")
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _render_plain_docx(
    conn: Connection,
    *,
    project_id: UUID,
    output_path: Path,
    volume_type: str | None = None,
) -> Path:
    project_name = _load_project_name(conn, project_id)
    with conn.cursor(row_factory=dict_row) as cur:
        if volume_type:
            drafts = cur.execute(
                """
                SELECT cd.chapter_code, cd.content_md, bc.chapter_title, bc.volume_type, bc.sort_order
                FROM chapter_draft cd
                LEFT JOIN bid_chapter bc ON bc.project_id = cd.project_id AND bc.chapter_code = cd.chapter_code
                WHERE cd.project_id = %s AND bc.volume_type = %s
                ORDER BY bc.sort_order NULLS LAST, cd.chapter_code
                """,
                (project_id, volume_type),
            ).fetchall()
        else:
            drafts = cur.execute(
                """
                SELECT cd.chapter_code, cd.content_md, bc.chapter_title, bc.volume_type, bc.sort_order
                FROM chapter_draft cd
                LEFT JOIN bid_chapter bc ON bc.project_id = cd.project_id AND bc.chapter_code = cd.chapter_code
                WHERE cd.project_id = %s
                ORDER BY bc.sort_order NULLS LAST, cd.chapter_code
                """,
                (project_id,),
            ).fetchall()

    document = Document()
    _apply_basic_style(document)
    title = f"{project_name} 投标文件"
    if volume_type:
        title += f"（{volume_type} 分册）"
    document.add_heading(title, level=0)
    document.add_paragraph("本文件由系统根据已确认招标约束、企业资料和章节草稿生成。")
    document.add_page_break()
    document.add_heading("目录", level=1)
    for draft in drafts:
        document.add_paragraph(f"{draft['chapter_code']} {draft.get('chapter_title') or ''}".strip())
    document.add_heading("附件清单", level=1)
    document.add_paragraph("资质证书、人员证书、业绩证明等附件按招标文件要求随交付包一并提交。")
    document.add_heading("签章位置", level=1)
    document.add_paragraph("投标人盖章：____________")
    document.add_paragraph("法定代表人或授权代表签字：____________")
    document.add_page_break()
    for index, draft in enumerate(drafts):
        if index:
            document.add_page_break()
        _add_markdown_content(document, draft["content_md"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output_path))
    return output_path


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

    if output_path is None:
        EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
        output_path = EXPORT_ROOT / str(project_id) / f"bid-{project_id}.docx"

    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        return _render_plain_docx(conn, project_id=project_id, output_path=output_path)

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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    overrides = load_tender_requirement_overrides(conn, project_id=project_id)
    if overrides["content_requirements"] or overrides["format_requirements"]:
        document = Document(str(output_path))
        document.add_page_break()
        document.add_heading("招标文件解析要求优先响应", level=1)
        document.add_paragraph("以下内容由招标文件解析结果生成，内容与格式要求优先于模板默认内容；如有冲突，按本节要求执行。")
        if overrides["content_requirements"]:
            document.add_heading("内容要求", level=2)
            for req in overrides["content_requirements"]:
                document.add_paragraph(str(req.get("requirement_text") or req.get("source_text") or req.get("title") or ""))
        if overrides["format_requirements"]:
            document.add_heading("格式要求", level=2)
            for req in overrides["format_requirements"]:
                document.add_paragraph(str(req.get("requirement_text") or req.get("source_text") or req.get("title") or ""))
        document.save(str(output_path))

    logger.info("docx_rendered", project_id=str(project_id), output=str(output_path))
    return output_path


def render_volume_docx(
    conn: Connection,
    *,
    project_id: UUID,
    volume_type: str,
    output_path: Path | None = None,
) -> Path:
    if output_path is None:
        output_path = EXPORT_ROOT / str(project_id) / f"bid-{volume_type}-{project_id}.docx"
    return _render_plain_docx(conn, project_id=project_id, volume_type=volume_type, output_path=output_path)


_FILENAME_SAFE_RE = re.compile(r"[\\/:*?\"<>|\r\n\t]+")


def _safe_filename_segment(value: str, fallback: str = "chapter") -> str:
    cleaned = _FILENAME_SAFE_RE.sub("_", value).strip(" ._-")
    return cleaned or fallback


def _load_chapter_drafts(conn: Connection, project_id: UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT cd.chapter_code, cd.content_md, bc.chapter_title, bc.volume_type, bc.sort_order
            FROM chapter_draft cd
            LEFT JOIN bid_chapter bc ON bc.project_id = cd.project_id AND bc.chapter_code = cd.chapter_code
            WHERE cd.project_id = %s
            ORDER BY bc.sort_order NULLS LAST, cd.chapter_code
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _render_chapter_docx(
    *,
    project_name: str,
    draft: dict,
    output_path: Path,
) -> Path:
    document = Document()
    _apply_basic_style(document)
    chapter_code = str(draft.get("chapter_code") or "").strip()
    chapter_title = str(draft.get("chapter_title") or "").strip()
    heading = " ".join(part for part in (chapter_code, chapter_title) if part) or "章节"
    document.add_heading(f"{project_name} 投标文件", level=0)
    document.add_heading(heading, level=1)
    _add_markdown_content(document, draft.get("content_md") or "")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output_path))
    return output_path


def _chapter_filename(draft: dict, index: int, suffix: str) -> str:
    chapter_code = str(draft.get("chapter_code") or "").strip()
    chapter_title = str(draft.get("chapter_title") or "").strip()
    code_segment = _safe_filename_segment(chapter_code, fallback=f"ch{index + 1:02d}")
    title_segment = _safe_filename_segment(chapter_title, fallback="")
    base = f"{index + 1:02d}_{code_segment}"
    if title_segment:
        base = f"{base}_{title_segment}"
    return f"{base}{suffix}"


def _default_zip_path(project_id: UUID, suffix: str) -> Path:
    return EXPORT_ROOT / str(project_id) / f"bid-chapters-{suffix}-{project_id}.zip"


def render_chapter_docx_zip(
    conn: Connection,
    *,
    project_id: UUID,
    output_path: Path | None = None,
) -> Path:
    """Render each chapter draft into its own .docx and pack into a zip."""
    drafts = _load_chapter_drafts(conn, project_id)
    if not drafts:
        raise ValueError("no chapter drafts found for project")

    project_name = _load_project_name(conn, project_id)
    if output_path is None:
        output_path = _default_zip_path(project_id, "docx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    work_dir = output_path.parent / f"_chapters-docx-{project_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    chapter_paths: list[tuple[str, Path]] = []
    for index, draft in enumerate(drafts):
        filename = _chapter_filename(draft, index, ".docx")
        chapter_path = work_dir / filename
        _render_chapter_docx(project_name=project_name, draft=draft, output_path=chapter_path)
        chapter_paths.append((filename, chapter_path))

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, path in chapter_paths:
            archive.write(path, filename)

    logger.info(
        "chapter_docx_zip_rendered",
        project_id=str(project_id),
        output=str(output_path),
        chapter_count=len(chapter_paths),
    )
    return output_path


def render_chapter_doc_zip(
    conn: Connection,
    *,
    project_id: UUID,
    output_path: Path | None = None,
) -> Path:
    """Render each chapter draft into a .docx, convert to legacy .doc, pack into zip."""
    drafts = _load_chapter_drafts(conn, project_id)
    if not drafts:
        raise ValueError("no chapter drafts found for project")

    project_name = _load_project_name(conn, project_id)
    if output_path is None:
        output_path = _default_zip_path(project_id, "doc")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    work_dir = output_path.parent / f"_chapters-doc-{project_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    converted: list[tuple[str, Path]] = []
    failures: list[str] = []
    for index, draft in enumerate(drafts):
        docx_filename = _chapter_filename(draft, index, ".docx")
        docx_path = work_dir / docx_filename
        _render_chapter_docx(project_name=project_name, draft=draft, output_path=docx_path)
        doc_path = convert_docx_to_doc(docx_path)
        if doc_path is None:
            failures.append(docx_filename)
            continue
        converted.append((_chapter_filename(draft, index, ".doc"), doc_path))

    if failures:
        raise RuntimeError(
            "DOC conversion unavailable or failed for chapters: " + ", ".join(failures)
        )

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, path in converted:
            archive.write(path, filename)

    logger.info(
        "chapter_doc_zip_rendered",
        project_id=str(project_id),
        output=str(output_path),
        chapter_count=len(converted),
    )
    return output_path


def render_export(
    conn: Connection,
    *,
    project_id: UUID,
    mode: str = EXPORT_MODE_SINGLE_DOCX,
    template_name: str = "default_technical_bid.docx",
    output_path: Path | None = None,
) -> Path:
    """Dispatch export rendering based on the requested mode."""
    if mode == EXPORT_MODE_SINGLE_DOCX:
        return render_docx(
            conn,
            project_id=project_id,
            template_name=template_name,
            output_path=output_path,
        )
    if mode == EXPORT_MODE_MULTI_DOCX_ZIP:
        return render_chapter_docx_zip(conn, project_id=project_id, output_path=output_path)
    if mode == EXPORT_MODE_MULTI_DOC_ZIP:
        return render_chapter_doc_zip(conn, project_id=project_id, output_path=output_path)
    raise ValueError(f"unsupported export mode: {mode}")
