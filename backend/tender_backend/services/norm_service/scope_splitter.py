"""Split compressed page windows into processing scopes.

Two scope types:
  - normative: main body clauses (hard constraints)
  - commentary: explanatory notes (条文说明)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from tender_backend.services.norm_service.layout_compressor import PageWindow

logger = structlog.stdlib.get_logger(__name__)

# Boundary patterns that signal the start of commentary sections
_COMMENTARY_BOUNDARIES = [
    re.compile(r"条文说明"),
    re.compile(r"附录\s*[A-Z]?\s*[（(]?资料性"),
    re.compile(r"本规范用词说明"),
    re.compile(r"引用标准名录"),
]
_TOC_PAGE_REF = re.compile(r"(?:\(\d+\)|（\d+）)\s*$")
_TOC_DOT_LEADERS = re.compile(r"[.…]{2,}")

# Candidate numeric headings. We further filter them to avoid treating
# full clause sentences as chapter boundaries.
_CHAPTER_PATTERN = re.compile(r"^\d+[ \t]+.+$", re.MULTILINE)
_CLAUSE_HEADING_PATTERN = re.compile(r"^\d+(?:\.\d+){2,}\s+\S")
_CLAUSE_PUNCTUATION = ("，", "。", "；", "：", ":", "!", "?", "！", "？")
_MAX_HEADING_LENGTH = 60
_DEFAULT_SCOPE_MAX_CHARS = 3000
_DEFAULT_SCOPE_MAX_CLAUSE_BLOCKS = 4
_TABLE_ROW_PATTERN = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)


@dataclass
class ProcessingScope:
    """A slice of the standard document for one LLM call."""

    scope_type: str  # "normative" | "commentary"
    chapter_label: str  # e.g. "3 结构设计" or "条文说明"
    text: str
    page_start: int
    page_end: int
    section_ids: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    context: dict[str, object] | None = None
    source_chunks: list[dict[str, object]] = field(default_factory=list)


def _detect_commentary_start(text: str) -> int | None:
    """Return char offset where commentary section begins, or None."""
    candidates: list[tuple[int, int, re.Match[str]]] = []
    for index, pattern in enumerate(_COMMENTARY_BOUNDARIES):
        for match in pattern.finditer(text):
            candidates.append((match.start(), index, match))

    candidates.sort(key=lambda item: (item[0], item[1]))
    for _start, _index, match in candidates:
        if _is_stray_commentary_heading(text, match):
            continue
        return match.start()
    return None


def _strip_stray_commentary_headings(text: str) -> str:
    candidates: list[tuple[int, int]] = []
    for match in re.finditer(r"(?m)^条文说明\s*$", text):
        if not _is_stray_commentary_heading(text, match):
            continue
        start = match.start()
        end = match.end()
        while start > 0 and text[start - 1] == "\n":
            start -= 1
        while end < len(text) and text[end] == "\n":
            end += 1
        candidates.append((start, end))

    if not candidates:
        return text

    result = text
    for start, end in reversed(candidates):
        left = result[:start].rstrip("\n")
        right = result[end:].lstrip("\n")
        if left and right:
            result = f"{left}\n\n{right}"
        else:
            result = left or right
    return result.strip()


def _iter_top_level_chapter_positions(text: str) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for match in _CHAPTER_PATTERN.finditer(text):
        line = match.group(0).strip()
        if not _is_top_level_heading(line):
            continue
        positions.append((match.start(), int(line.split(None, 1)[0])))
    return positions


def _line_at(text: str, offset: int) -> str:
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()


def _is_stray_commentary_heading(text: str, match: re.Match[str]) -> bool:
    if _line_at(text, match.start()) != "条文说明":
        return False

    previous_chapter: int | None = None
    next_chapter: int | None = None
    for chapter_start, chapter_no in _iter_top_level_chapter_positions(text):
        if chapter_start < match.start():
            previous_chapter = chapter_no
            continue
        if chapter_start > match.start():
            next_chapter = chapter_no
            break

    return (
        previous_chapter is not None
        and next_chapter is not None
        and next_chapter == previous_chapter + 1
    )


def _is_top_level_heading(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) > _MAX_HEADING_LENGTH:
        return False
    if any(mark in stripped for mark in _CLAUSE_PUNCTUATION):
        return False
    return True


def _looks_like_toc_window(text: str) -> bool:
    informative_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and line.strip().lower() not in {"text", "text_list"}
    ]
    if len(informative_lines) < 3:
        return False

    toc_like_count = sum(
        1
        for line in informative_lines
        if _TOC_PAGE_REF.search(line) or _TOC_DOT_LEADERS.search(line)
    )
    return toc_like_count >= 3 and toc_like_count * 2 >= len(informative_lines)


def _split_by_chapters(text: str, page_start: int, page_end: int,
                       section_ids: list[str], scope_type: str) -> list[ProcessingScope]:
    """Split a text block by top-level chapter headings."""
    matches = []
    expected_chapter_no: int | None = None
    for match in _CHAPTER_PATTERN.finditer(text):
        line = match.group(0).strip()
        if not _is_top_level_heading(line):
            continue

        chapter_no = int(line.split(None, 1)[0])
        if expected_chapter_no is None:
            matches.append(match)
            expected_chapter_no = chapter_no + 1
            continue

        if chapter_no != expected_chapter_no:
            continue

        matches.append(match)
        expected_chapter_no += 1
    if not matches:
        return [ProcessingScope(
            scope_type=scope_type,
            chapter_label=scope_type,
            text=text,
            page_start=page_start,
            page_end=page_end,
            section_ids=section_ids,
        )]

    scopes: list[ProcessingScope] = []

    # Text before first chapter (preamble)
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            scopes.append(ProcessingScope(
                scope_type=scope_type,
                chapter_label="前言",
                text=preamble,
                page_start=page_start,
                page_end=page_start,
                section_ids=section_ids,
            ))

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if not chunk:
            continue

        # Extract chapter label from first line
        first_line = chunk.split("\n", 1)[0].strip()
        scopes.append(ProcessingScope(
            scope_type=scope_type,
            chapter_label=first_line[:60],
            text=chunk,
            page_start=page_start,
            page_end=page_end,
            section_ids=section_ids,
        ))

    return scopes


def split_into_scopes(windows: list[PageWindow]) -> list[ProcessingScope]:
    """Split page windows into normative and commentary scopes."""
    if not windows:
        return []

    filtered_windows = [window for window in windows if not _looks_like_toc_window(window.text)]
    if filtered_windows:
        windows = filtered_windows

    # Concatenate all windows
    full_text = "\n\n".join(w.text for w in windows)
    full_text = _strip_stray_commentary_headings(full_text)
    all_ids = [sid for w in windows for sid in w.section_ids]
    first_page = windows[0].page_start
    last_page = windows[-1].page_end

    # Detect commentary boundary
    boundary = _detect_commentary_start(full_text)

    if boundary is not None:
        normative_text = full_text[:boundary].strip()
        commentary_text = full_text[boundary:].strip()
    else:
        normative_text = full_text
        commentary_text = ""

    scopes: list[ProcessingScope] = []

    # Split normative body by chapters
    if normative_text:
        scopes.extend(_split_by_chapters(
            normative_text, first_page, last_page, all_ids, "normative",
        ))

    # Split commentary by chapters
    if commentary_text:
        scopes.extend(_split_by_chapters(
            commentary_text, first_page, last_page, all_ids, "commentary",
        ))

    logger.info(
        "scopes_split",
        total_scopes=len(scopes),
        normative=[s.chapter_label for s in scopes if s.scope_type == "normative"],
        commentary=[s.chapter_label for s in scopes if s.scope_type == "commentary"],
    )
    return scopes


def _split_block_by_paragraphs(text: str, max_chars: int) -> list[str]:
    """Split a text block into paragraph-based parts within the character budget."""
    stripped = text.strip()
    if stripped.lower().startswith("<table") and stripped.lower().endswith("</table>"):
        row_parts = _split_html_table_by_rows(stripped, max_chars)
        if len(row_parts) > 1:
            return row_parts

    parts: list[str] = []
    current = ""
    for paragraph in [p.strip() for p in text.split("\n\n") if p.strip()]:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        parts.append(current)
    if len(parts) == 1 and len(parts[0]) > max_chars and "\n" in stripped:
        line_parts = _split_block_by_lines(stripped, max_chars)
        if len(line_parts) > 1:
            return line_parts
    return parts


def _split_block_by_lines(text: str, max_chars: int) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return [text]

    parts: list[str] = []
    current = ""
    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = line
        else:
            current = candidate

    if current:
        parts.append(current)
    return parts or [text]


def _split_html_table_by_rows(text: str, max_chars: int) -> list[str]:
    """Split a large HTML table into smaller valid table fragments by row."""
    rows = _TABLE_ROW_PATTERN.findall(text)
    if len(rows) <= 1:
        return [text]

    open_end = text.lower().find(">")
    close_start = text.lower().rfind("</table>")
    if open_end == -1 or close_start == -1 or close_start <= open_end:
        return [text]

    table_open = text[: open_end + 1]
    table_close = text[close_start:]
    parts: list[str] = []
    current_rows: list[str] = []

    for row in rows:
        candidate_rows = [*current_rows, row]
        candidate = f"{table_open}{''.join(candidate_rows)}{table_close}"
        if current_rows and len(candidate) > max_chars:
            parts.append(f"{table_open}{''.join(current_rows)}{table_close}")
            current_rows = [row]
        else:
            current_rows = candidate_rows

    if current_rows:
        parts.append(f"{table_open}{''.join(current_rows)}{table_close}")
    return parts or [text]


def _split_into_clause_blocks(text: str) -> list[tuple[str, int]]:
    """Group paragraphs by clause heading so one chunk doesn't span too many clauses."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    blocks: list[tuple[str, int]] = []
    preamble: list[str] = []
    current: list[str] = []
    clause_index = 0

    for paragraph in paragraphs:
        if _CLAUSE_HEADING_PATTERN.match(paragraph):
            if current:
                blocks.append(("\n\n".join(current), clause_index))
            clause_index += 1
            current = [*preamble, paragraph] if clause_index == 1 and preamble else [paragraph]
            preamble = []
            continue

        if clause_index == 0:
            preamble.append(paragraph)
        else:
            current.append(paragraph)

    if current:
        blocks.append(("\n\n".join(current), clause_index))
    elif preamble:
        blocks.append(("\n\n".join(preamble), 0))

    return blocks


def rebalance_scopes(
    scopes: list[ProcessingScope],
    *,
    max_chars: int = _DEFAULT_SCOPE_MAX_CHARS,
    max_clause_blocks: int = _DEFAULT_SCOPE_MAX_CLAUSE_BLOCKS,
) -> list[ProcessingScope]:
    """Split oversized scopes by paragraph blocks to avoid long LLM timeouts."""
    if not scopes:
        return []

    rebalanced: list[ProcessingScope] = []

    def _dedupe_refs(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    def _select_source_chunks(part_text: str, source_chunks: list[dict[str, object]]) -> list[dict[str, object]]:
        if not source_chunks:
            return []

        full_text = "\n\n".join(str(chunk.get("text") or "") for chunk in source_chunks)
        offsets: list[tuple[int, int, dict[str, object]]] = []
        cursor = 0
        for index, chunk in enumerate(source_chunks):
            chunk_text = str(chunk.get("text") or "")
            if index > 0:
                cursor += 2
            start = cursor
            end = start + len(chunk_text)
            offsets.append((start, end, chunk))
            cursor = end

        start = full_text.find(part_text)
        if start == -1:
            return []
        end = start + len(part_text)
        return [
            chunk
            for chunk_start, chunk_end, chunk in offsets
            if chunk_end > start and chunk_start < end
        ]

    def _derive_child_provenance(scope: ProcessingScope, part_text: str) -> tuple[list[str], dict[str, object] | None, list[dict[str, object]]]:
        if not scope.source_chunks:
            return scope.source_refs, scope.context, scope.source_chunks

        child_chunks = _select_source_chunks(part_text, scope.source_chunks)
        if not child_chunks:
            return scope.source_refs, scope.context, scope.source_chunks

        child_refs = _dedupe_refs(
            [str(chunk.get("source_ref")) for chunk in child_chunks if chunk.get("source_ref")]
        )

        child_context = scope.context
        if isinstance(scope.context, dict):
            child_context = dict(scope.context)
            child_context["source_refs"] = child_refs
            child_context["node_types"] = [
                str(chunk.get("node_type"))
                for chunk in child_chunks
                if chunk.get("node_type")
            ]

        return child_refs, child_context, child_chunks

    for scope in scopes:
        clause_blocks = _split_into_clause_blocks(scope.text)
        clause_block_count = max((block_id for _, block_id in clause_blocks), default=0)

        if len(scope.text) <= max_chars and clause_block_count <= max_clause_blocks:
            rebalanced.append(scope)
            continue

        units = clause_blocks or [(scope.text.strip(), 0)]
        expanded_units: list[tuple[str, int]] = []
        for text, block_id in units:
            if len(text) <= max_chars:
                expanded_units.append((text, block_id))
                continue
            for part in _split_block_by_paragraphs(text, max_chars):
                expanded_units.append((part, block_id))

        parts: list[tuple[str, set[int]]] = []
        current = ""
        current_clause_blocks: set[int] = set()
        for text, block_id in expanded_units:
            candidate = text if not current else f"{current}\n\n{text}"
            candidate_clause_blocks = set(current_clause_blocks)
            if block_id > 0:
                candidate_clause_blocks.add(block_id)

            if (
                current
                and (
                    len(candidate) > max_chars
                    or len(candidate_clause_blocks) > max_clause_blocks
                )
            ):
                parts.append((current, current_clause_blocks))
                current = text
                current_clause_blocks = {block_id} if block_id > 0 else set()
            else:
                current = candidate
                current_clause_blocks = candidate_clause_blocks

        if current:
            parts.append((current, current_clause_blocks))

        if len(parts) <= 1:
            rebalanced.append(scope)
            continue

        total_parts = len(parts)
        for idx, (part, _) in enumerate(parts, start=1):
            child_source_refs, child_context, child_chunks = _derive_child_provenance(scope, part)
            rebalanced.append(ProcessingScope(
                scope_type=scope.scope_type,
                chapter_label=f"{scope.chapter_label} ({idx}/{total_parts})",
                text=part,
                page_start=scope.page_start,
                page_end=scope.page_end,
                section_ids=scope.section_ids,
                source_refs=child_source_refs,
                context=child_context,
                source_chunks=child_chunks,
            ))

    return rebalanced
