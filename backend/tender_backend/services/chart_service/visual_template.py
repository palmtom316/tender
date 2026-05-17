"""招标图表视觉规范常量。

被 chart_service.vega_mapper、chart_service.renderers、tests 共享，
确保不同引擎渲染出的图表保持同一套配色 / 字号 / 比例语言。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaletteSpec:
    primary: str
    primary_dark: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_muted: str
    risk_low: str
    risk_medium: str
    risk_high: str
    risk_critical: str
    risk_default: str


@dataclass(frozen=True)
class FontSpec:
    family: str
    title_px: int
    subtitle_px: int
    axis_label_px: int
    cell_text_px: int
    legend_px: int
    min_px: int


@dataclass(frozen=True)
class PageSpec:
    a4_portrait_width_pt: int
    a4_landscape_width_pt: int
    matrix_max_aspect_ratio: float
    matrix_min_aspect_ratio: float
    docx_image_width_in: float


@dataclass(frozen=True)
class VisualTemplate:
    palette: PaletteSpec
    font: FontSpec
    page: PageSpec


PALETTE = PaletteSpec(
    primary="#1f4e79",
    primary_dark="#173e60",
    surface="#ffffff",
    surface_alt="#f1f5f9",
    border="#8b98a8",
    text="#1f2933",
    text_muted="#4c5661",
    risk_low="#e7f5e8",
    risk_medium="#fff4ce",
    risk_high="#ffe0cc",
    risk_critical="#ffd6d6",
    risk_default="#ffffff",
)


FONT = FontSpec(
    family="Noto Sans CJK SC, Microsoft YaHei, SimSun, sans-serif",
    title_px=18,
    subtitle_px=14,
    axis_label_px=13,
    cell_text_px=12,
    legend_px=11,
    min_px=9,
)


PAGE = PageSpec(
    a4_portrait_width_pt=595,
    a4_landscape_width_pt=842,
    matrix_max_aspect_ratio=1.5,
    matrix_min_aspect_ratio=0.6,
    docx_image_width_in=6.0,
)


VISUAL_TEMPLATE = VisualTemplate(palette=PALETTE, font=FONT, page=PAGE)


RISK_LEVEL_COLORS: dict[str, str] = {
    "low": PALETTE.risk_low,
    "medium": PALETTE.risk_medium,
    "high": PALETTE.risk_high,
    "critical": PALETTE.risk_critical,
}


def risk_color(level: str | None) -> str:
    return RISK_LEVEL_COLORS.get(level or "", PALETTE.risk_default)
