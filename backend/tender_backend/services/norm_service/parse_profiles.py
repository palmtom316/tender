"""Per-standard parse profile configuration.

A `ParseProfile` centralises the heuristics that used to be sprinkled across
`block_segments.py`, `structural_nodes.py`, `outline_rebuilder.py`, and
`norm_processor.py` as hard-coded regex constants. Each profile bundles the
lexical markers, appendix/commentary patterns, and acceptance thresholds for
one family of standards (e.g. Chinese building codes `cn_gb`).

`resolve_profile()` is the single entry point the processing pipeline calls.
The `cn_gb` profile reproduces today's behaviour for GB 50148-2010 and its
siblings (GB 50147, GB 50150) so adopting it is not a semantic change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParseProfile:
    code: str

    # Commentary section boundary detection
    commentary_boundary_lines: tuple[str, ...]
    commentary_appendix_only_lines: tuple[str, ...]
    non_normative_back_matter_lines: tuple[str, ...]
    commentary_title_hints: tuple[str, ...]

    # Non-clause / boilerplate titles that should never become clauses
    non_clause_titles: tuple[str, ...]
    non_clause_text_fragments: tuple[str, ...]

    # Clause / appendix numbering
    appendix_code_pattern: re.Pattern
    leading_clause_no_pattern: re.Pattern
    list_item_code_pattern: re.Pattern

    # Table-of-contents noise
    toc_page_ref_pattern: re.Pattern
    toc_dot_leaders_pattern: re.Pattern

    # Clause-text sentence heuristics
    sentence_signal_pattern: re.Pattern

    # Acceptance thresholds (used by tests and `needs_review` gating)
    min_total_clauses: int = 0
    must_have_clause_nos: tuple[str, ...] = ()
    target_commentary_min: int = 0


def _compile_non_clause_titles(titles: tuple[str, ...]) -> re.Pattern:
    alternation = "|".join(re.escape(t) for t in titles)
    return re.compile(rf"^({alternation})$")


def _compile_non_clause_text_fragments(fragments: tuple[str, ...]) -> re.Pattern:
    alternation = "|".join(re.escape(f) for f in fragments)
    return re.compile(f"({alternation})")


# ── cn_gb: Chinese national building-code family (GB 5xxxx, DL/T, JGJ) ──

_CN_GB_NON_CLAUSE_TITLES = (
    "本规范用词说明",
    "引用标准名录",
    "修订说明",
    "目次",
    "前言",
)

_CN_GB_NON_CLAUSE_TEXT_FRAGMENTS = (
    "为便于在执行本规范条文时区别对待",
    "条文中指明应按其他有关标准执行",
)

CN_GB_PROFILE = ParseProfile(
    code="cn_gb",
    commentary_boundary_lines=("附：条文说明", "附:条文说明", "条文说明"),
    commentary_appendix_only_lines=("附：条文说明", "附:条文说明"),
    non_normative_back_matter_lines=("本规范用词说明", "引用标准名录"),
    commentary_title_hints=("条文说明",),
    non_clause_titles=_CN_GB_NON_CLAUSE_TITLES,
    non_clause_text_fragments=_CN_GB_NON_CLAUSE_TEXT_FRAGMENTS,
    appendix_code_pattern=re.compile(r"^[A-Z](?:\.\d+)*$"),
    leading_clause_no_pattern=re.compile(
        r"^\s*((?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)+))\b"
    ),
    list_item_code_pattern=re.compile(r"^\d+$"),
    toc_page_ref_pattern=re.compile(r"(?:\(\d+\)|（\d+）)\s*$"),
    toc_dot_leaders_pattern=re.compile(r"[.…]{2,}"),
    sentence_signal_pattern=re.compile(r"[，。；：]|应|不得|必须|严禁|禁止|宜|可"),
    # Thresholds kept conservative; per-standard acceptance tests tighten them.
    min_total_clauses=0,
    must_have_clause_nos=(),
    target_commentary_min=0,
)


PROFILES: dict[str, ParseProfile] = {
    CN_GB_PROFILE.code: CN_GB_PROFILE,
}


def resolve_profile(code: str | None) -> ParseProfile:
    """Return the profile for `code`, falling back to `cn_gb` when unknown or empty."""
    if code:
        profile = PROFILES.get(code.strip())
        if profile is not None:
            return profile
    return CN_GB_PROFILE


def non_clause_title_pattern(profile: ParseProfile) -> re.Pattern:
    """Lazy-compile (and cache) the non-clause title alternation for a profile."""
    cache = getattr(non_clause_title_pattern, "_cache", None)
    if cache is None:
        cache = {}
        non_clause_title_pattern._cache = cache  # type: ignore[attr-defined]
    if profile.code not in cache:
        cache[profile.code] = _compile_non_clause_titles(profile.non_clause_titles)
    return cache[profile.code]


def non_clause_text_pattern(profile: ParseProfile) -> re.Pattern:
    cache = getattr(non_clause_text_pattern, "_cache", None)
    if cache is None:
        cache = {}
        non_clause_text_pattern._cache = cache  # type: ignore[attr-defined]
    if profile.code not in cache:
        cache[profile.code] = _compile_non_clause_text_fragments(
            profile.non_clause_text_fragments
        )
    return cache[profile.code]
