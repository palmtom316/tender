"""Deterministic normalization for standard-document requirement tables."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import Any


class TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[dict[str, object]]] = []
        self._current_row: list[dict[str, object]] | None = None
        self._current_cell: dict[str, object] | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
            return
        if tag in {"td", "th"} and self._current_row is not None:
            attr_map = dict(attrs)
            self._current_cell = {
                "rowspan": int(attr_map.get("rowspan") or 1),
                "colspan": int(attr_map.get("colspan") or 1),
            }
            self._text_parts = []
            return
        if tag == "br" and self._current_cell is not None:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            text = " ".join(unescape("".join(self._text_parts)).split())
            self._current_cell["text"] = text
            self._current_row.append(self._current_cell)
            self._current_cell = None
            self._text_parts = []
            return
        if tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._text_parts.append(data)


def expand_table_rows(table_html: str) -> list[list[str]]:
    parser = TableHTMLParser()
    parser.feed(table_html)

    expanded_rows: list[list[str]] = []
    pending: dict[int, tuple[int, str]] = {}

    for row in parser.rows:
        expanded: list[str] = []
        col_index = 0

        def consume_pending() -> None:
            nonlocal col_index
            while col_index in pending:
                remaining, text = pending[col_index]
                expanded.append(text)
                if remaining <= 1:
                    del pending[col_index]
                else:
                    pending[col_index] = (remaining - 1, text)
                col_index += 1

        consume_pending()
        for cell in row:
            consume_pending()
            text = str(cell.get("text") or "").strip()
            rowspan = max(1, int(cell.get("rowspan") or 1))
            colspan = max(1, int(cell.get("colspan") or 1))
            for _ in range(colspan):
                expanded.append(text)
                if rowspan > 1:
                    pending[col_index] = (rowspan - 1, text)
                col_index += 1
        consume_pending()
        if any(value.strip() for value in expanded):
            expanded_rows.append(expanded)

    return expanded_rows


def classify_table_strategy(
    table_title: str | None,
    rows: list[list[str]],
    *,
    default_strategy: str = "parameter_limit_table",
) -> str:
    title = str(table_title or "").strip()
    flattened = " ".join(cell for row in rows for cell in row if cell).strip()
    header = rows[0] if rows else []
    header_text = " ".join(header)
    combined = f"{title} {flattened}"

    if any(token in combined for token in ("检查记录", "验收记录", "记录表", "检查表")):
        return "form_template_table"
    if any(token in header_text for token in ("工程名称", "施工单位", "检查人", "日期")):
        return "form_template_table"
    if any(token in header_text for token in ("检验项目", "检查项目", "质量要求", "检验方法")):
        return "quality_inspection_table"
    if any(token in header_text for token in ("标准值", "允许偏差", "限值", "电压等级")):
        return "parameter_limit_table"
    if default_strategy in {
        "quality_inspection_table",
        "parameter_limit_table",
        "form_template_table",
        "non_requirement_table",
        "generic_table",
    }:
        return default_strategy
    return "parameter_limit_table"


def deterministic_table_entries_from_block(
    block: Any,
    *,
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    table_html = str(getattr(block, "table_html", None) or "").strip()
    table_title = str(getattr(block, "table_title", None) or "").strip()
    if not table_html or not table_title:
        return []
    page_start = getattr(block, "page_start", None)
    page_end = getattr(block, "page_end", None)
    if page_end is None:
        page_end = page_start

    rows = expand_table_rows(table_html)
    if len(rows) < 2:
        return []

    effective_strategy = strategy or classify_table_strategy(table_title, rows)
    if effective_strategy in {"form_template_table", "non_requirement_table"}:
        return []

    return _grouped_requirement_entries(
        block,
        rows,
        table_title=table_title,
        page_start=page_start,
        page_end=page_end,
        strategy=effective_strategy,
    )


def is_sparse_table_block(block: Any) -> bool:
    table_html = str(getattr(block, "table_html", None) or "").strip()
    if not table_html:
        return True
    rows = expand_table_rows(table_html)
    if len(rows) < 2:
        return True
    width = max((len(row) for row in rows), default=0)
    return width < 2


def _grouped_requirement_entries(
    block: Any,
    rows: list[list[str]],
    *,
    table_title: str,
    page_start: int | None,
    page_end: int | None,
    strategy: str,
) -> list[dict[str, Any]]:
    header = [cell.strip() for cell in rows[0]]
    width = max(len(header), *(len(row) for row in rows[1:]))
    if width < 2:
        return []
    header += [""] * (width - len(header))

    grouped_rows: dict[str, list[str]] = {}
    grouped_remarks: dict[str, list[str]] = {}

    for raw_row in rows[1:]:
        row = list(raw_row) + [""] * (width - len(raw_row))
        primary = row[0].strip()
        if not primary:
            continue

        row_parts: list[str] = []
        remark_parts = grouped_remarks.setdefault(primary, [])
        for index, cell in enumerate(row[1:], start=1):
            cell_text = cell.strip()
            if not cell_text or cell_text == "-":
                continue
            column_name = header[index].strip() or f"列{index + 1}"
            if column_name == "备注":
                if cell_text not in remark_parts:
                    remark_parts.append(cell_text)
                continue
            row_parts.append(f"{column_name}{cell_text}")

        if row_parts:
            grouped_rows.setdefault(primary, []).append("，".join(row_parts))

    entries: list[dict[str, Any]] = []
    source_refs = list(getattr(block, "source_refs", []) or [])
    for primary, row_parts in grouped_rows.items():
        sentence_parts = list(row_parts)
        remarks = grouped_remarks.get(primary, [])
        if remarks:
            sentence_parts.append(f"备注：{'；'.join(remarks)}")
        clause_text = f"{primary}：" + "；".join(sentence_parts) + "。"
        entries.append({
            "clause_no": None,
            "clause_title": table_title,
            "clause_text": clause_text,
            "summary": None,
            "tags": [],
            "page_start": page_start,
            "page_end": page_end,
            "clause_type": "normative",
            "source_type": "table",
            "source_ref": source_refs[0] if source_refs else None,
            "source_refs": source_refs,
            "source_label": getattr(block, "chapter_label", None),
            "table_strategy": strategy,
        })

    return entries
