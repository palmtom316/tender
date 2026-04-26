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

_CN_GB_CLAUSE_NO_FOLLOWER = r"(?=$|[\s（(：:，。；、\-－\u4e00-\u9fff])"
_CN_GB_NUMERIC_CLAUSE_NO = r"\d{1,2}(?:\.\d{1,2})*"
_CN_GB_APPENDIX_CLAUSE_NO = r"[A-Z](?:\.\d{1,2})*"
_CN_GB_COMPACT_CLAUSE_PREFIX_RE = re.compile(
    r"^\s*((?:[A-Z](?:\.\d+)*|\d+(?:\.\d+)*))(.*)$"
)
_CN_GB_ABSORBED_UNIT_RE = re.compile(
    r"^\s*(\d{1,4})\s*(?:kV|kW|MVar|MVA|MV·A|V|A)(?=$|[\s（(：:，。；、\-－\u4e00-\u9fff])",
    re.IGNORECASE,
)
_CN_GB_COMMON_UNIT_PREFIXES = {
    "1",
    "3",
    "6",
    "10",
    "20",
    "35",
    "66",
    "110",
    "220",
    "330",
    "500",
    "750",
    "1000",
}


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

    clause_heading_patterns: tuple[re.Pattern, ...] = field(default_factory=tuple)
    appendix_heading_patterns: tuple[re.Pattern, ...] = field(default_factory=tuple)
    commentary_heading_patterns: tuple[re.Pattern, ...] = field(default_factory=tuple)
    list_item_patterns: tuple[re.Pattern, ...] = field(default_factory=tuple)
    table_requirement_strategy: str = "parameter_limit_table"
    deterministic_block_parser: bool = True
    quality_thresholds: dict[str, float | int] = field(default_factory=dict)

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
    "为便于在执行本标准条文时区别对待",
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
        rf"^\s*((?:{_CN_GB_APPENDIX_CLAUSE_NO}|{_CN_GB_NUMERIC_CLAUSE_NO})){_CN_GB_CLAUSE_NO_FOLLOWER}"
    ),
    list_item_code_pattern=re.compile(r"^\d+$"),
    clause_heading_patterns=(
        re.compile(r"^\d+(?:\.\d+){2,}$"),
        re.compile(r"^\s*\d+(?:\.\d+){2,}\b"),
    ),
    appendix_heading_patterns=(
        re.compile(r"^[A-Z]\.\d+(?:\.\d+)*$"),
        re.compile(r"^\s*附录\s*[A-Z]\b"),
    ),
    commentary_heading_patterns=(
        re.compile(r"^\s*(附[:：])?条文说明\s*$"),
        re.compile(r"^\s*修订说明\s*$"),
    ),
    list_item_patterns=(
        re.compile(r"^\d+$"),
        re.compile(r"^\s*\d+[、.)）]\s*"),
        re.compile(r"^\s*[（(]\d+[）)]\s*"),
    ),
    table_requirement_strategy="parameter_limit_table",
    quality_thresholds={
        "min_anchor_coverage": 0.95,
        "max_validation_issues": 5,
        "max_ai_fallback_ratio": 0.15,
    },
    toc_page_ref_pattern=re.compile(r"(?:\(\d+\)|（\d+）)\s*$"),
    toc_dot_leaders_pattern=re.compile(r"[.…]{2,}"),
    sentence_signal_pattern=re.compile(r"[，。；：]|应|不得|必须|严禁|禁止|宜|可"),
    # Thresholds kept conservative; per-standard acceptance tests tighten them.
    min_total_clauses=0,
    must_have_clause_nos=(),
    target_commentary_min=0,
)

GENERIC_ENTERPRISE_PROFILE = ParseProfile(
    code="generic_enterprise",
    commentary_boundary_lines=("Commentary", "Notes"),
    commentary_appendix_only_lines=(),
    non_normative_back_matter_lines=("References", "Bibliography"),
    commentary_title_hints=("Commentary", "Notes"),
    non_clause_titles=("Preface", "Foreword", "References"),
    non_clause_text_fragments=(),
    appendix_code_pattern=re.compile(r"^APP-[A-Z0-9]+$"),
    leading_clause_no_pattern=re.compile(r"^\s*((?:REQ|SEC)-\d+(?:\.\d+)*)\b", re.I),
    list_item_code_pattern=re.compile(r"^\d+$"),
    clause_heading_patterns=(
        re.compile(r"^(?:REQ|SEC)-\d+(?:\.\d+)*$", re.I),
        re.compile(r"^\s*(?:REQ|SEC)-\d+(?:\.\d+)*\b", re.I),
    ),
    appendix_heading_patterns=(re.compile(r"^APP-[A-Z0-9]+$", re.I),),
    commentary_heading_patterns=(re.compile(r"^\s*(Commentary|Notes)\s*$", re.I),),
    list_item_patterns=(re.compile(r"^\d+$"), re.compile(r"^\s*\d+[.)]\s*")),
    table_requirement_strategy="generic_table",
    quality_thresholds={
        "min_anchor_coverage": 0.9,
        "max_validation_issues": 10,
        "max_ai_fallback_ratio": 0.2,
    },
    toc_page_ref_pattern=re.compile(r"\s+\d+\s*$"),
    toc_dot_leaders_pattern=re.compile(r"[.]{2,}"),
    sentence_signal_pattern=re.compile(r"\b(shall|must|should|may|required)\b|[.;:]", re.I),
)


PROFILES: dict[str, ParseProfile] = {
    CN_GB_PROFILE.code: CN_GB_PROFILE,
    GENERIC_ENTERPRISE_PROFILE.code: GENERIC_ENTERPRISE_PROFILE,
}


def resolve_profile(code: str | None) -> ParseProfile:
    """Return the profile for `code`, falling back to `cn_gb` when unknown or empty."""
    if code:
        profile = PROFILES.get(code.strip())
        if profile is not None:
            return profile
    return CN_GB_PROFILE


def extract_leading_clause_no(
    value: str | None,
    *,
    profile: ParseProfile = CN_GB_PROFILE,
) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = profile.leading_clause_no_pattern.match(text)
    if not match:
        if profile is not CN_GB_PROFILE:
            return None
        compact_match = _CN_GB_COMPACT_CLAUSE_PREFIX_RE.match(text)
        if not compact_match:
            return None
        candidate = str(compact_match.group(1) or "").strip()
        remainder = str(compact_match.group(2) or "")
        if "." not in candidate:
            return None

        parts = candidate.split(".")
        last_segment = parts[-1]
        best: tuple[int, str] | None = None
        for split_pos in range(1, len(last_segment)):
            clause_tail = last_segment[:split_pos]
            if not clause_tail or len(clause_tail) > 2:
                continue
            absorbed = last_segment[split_pos:] + remainder
            absorbed_match = _CN_GB_ABSORBED_UNIT_RE.match(absorbed)
            if not absorbed_match:
                continue
            unit_prefix = str(absorbed_match.group(1) or "").lstrip("0") or "0"
            if unit_prefix not in _CN_GB_COMMON_UNIT_PREFIXES:
                continue
            resolved = ".".join(parts[:-1] + [clause_tail])
            score = len(unit_prefix)
            if best is None or score > best[0] or (score == best[0] and len(resolved) > len(best[1])):
                best = (score, resolved)
        return best[1] if best is not None else None
    return match.group(1)


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
