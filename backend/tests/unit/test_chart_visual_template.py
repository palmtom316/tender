from __future__ import annotations

from tender_backend.services.chart_service.visual_template import (
    FONT,
    PAGE,
    PALETTE,
    RISK_LEVEL_COLORS,
    VISUAL_TEMPLATE,
    risk_color,
)


def test_visual_template_exposes_palette_font_and_page() -> None:
    assert VISUAL_TEMPLATE.palette is PALETTE
    assert VISUAL_TEMPLATE.font is FONT
    assert VISUAL_TEMPLATE.page is PAGE


def test_font_min_px_is_at_least_nine() -> None:
    assert FONT.min_px >= 9
    assert FONT.title_px > FONT.cell_text_px > FONT.legend_px >= FONT.min_px


def test_page_aspect_ratio_bounds_are_consistent() -> None:
    assert 0 < PAGE.matrix_min_aspect_ratio < 1 < PAGE.matrix_max_aspect_ratio


def test_risk_color_maps_known_levels_and_falls_back_to_default() -> None:
    for level, color in RISK_LEVEL_COLORS.items():
        assert risk_color(level) == color
    assert risk_color(None) == PALETTE.risk_default
    assert risk_color("unknown") == PALETTE.risk_default
