"""Technical chapter strategy registry."""

from __future__ import annotations

from .registry import (
    CHAPTER_STRATEGIES,
    DEFAULT_CHARTS,
    DEFAULT_TABLES,
    LONGFORM_CHAPTER_CONFIG,
    LONGFORM_SECTION_SETS,
    SECTION_WEIGHTS,
    SITE_CONDITION_KEYWORDS,
    TechnicalChapterStrategy,
    chart_recommendations_for_chapter,
    prompt_template_for_chapter,
    strategy_for_chapter,
)

__all__ = [
    "CHAPTER_STRATEGIES",
    "DEFAULT_CHARTS",
    "DEFAULT_TABLES",
    "LONGFORM_CHAPTER_CONFIG",
    "LONGFORM_SECTION_SETS",
    "SECTION_WEIGHTS",
    "SITE_CONDITION_KEYWORDS",
    "TechnicalChapterStrategy",
    "chart_recommendations_for_chapter",
    "prompt_template_for_chapter",
    "strategy_for_chapter",
]
