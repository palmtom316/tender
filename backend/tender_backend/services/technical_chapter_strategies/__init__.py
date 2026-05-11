"""Technical chapter strategy registry."""

from __future__ import annotations

from .registry import (
    CHAPTER_STRATEGIES,
    TechnicalChapterStrategy,
    chart_recommendations_for_chapter,
    prompt_template_for_chapter,
    strategy_for_chapter,
)

__all__ = [
    "CHAPTER_STRATEGIES",
    "TechnicalChapterStrategy",
    "chart_recommendations_for_chapter",
    "prompt_template_for_chapter",
    "strategy_for_chapter",
]
