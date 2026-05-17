"""Lightweight DOCX format checks for exported bid documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def check_docx_format(docx_path: Path | str) -> dict[str, Any]:
    """Return a non-throwing format check report for an exported DOCX.

    This v1 checker focuses on issues that can be detected cheaply and safely
    from the generated DOCX. It records evidence for export gates without making
    the gate blocking yet.
    """

    path = Path(docx_path)
    issues: list[dict[str, Any]] = []
    try:
        from docx import Document

        document = Document(path)
        for table_index, table in enumerate(document.tables, start=1):
            if not table.style or not str(table.style.name or "").strip():
                issues.append(
                    {
                        "code": "table_missing_style",
                        "severity": "P2",
                        "table_index": table_index,
                        "message": "表格未设置明确样式。",
                    }
                )
            if not _table_has_borders(table):
                issues.append(
                    {
                        "code": "table_missing_borders",
                        "severity": "P1",
                        "table_index": table_index,
                        "message": "表格缺少边框定义，导出后可能不可读。",
                    }
                )
    except Exception as exc:
        return {
            "format_passed": False,
            "format_status": "error",
            "format_message": f"格式校验失败：{exc}",
            "issues": [{"code": "format_check_error", "severity": "P1", "message": str(exc)}],
        }

    return {
        "format_passed": not any(issue.get("severity") in {"P0", "P1"} for issue in issues),
        "format_status": "passed" if not issues else "failed",
        "format_message": "格式检查通过。" if not issues else f"发现 {len(issues)} 项格式问题。",
        "issues": issues,
    }


def _table_has_borders(table: Any) -> bool:
    tbl = getattr(table, "_tbl", None)
    tbl_pr = tbl.tblPr if tbl is not None else None
    if tbl_pr is None:
        return False
    return tbl_pr.first_child_found_in("w:tblBorders") is not None
