from __future__ import annotations

import re
from pathlib import Path

from tender_backend.services.chart_service.specs import SUPPORTED_CHART_TYPES


PROMPT_FILES = [
    "配网施工方案及技术措施提示词.md",
    "配网工作规划描述提示词.md",
    "配网质量保证措施提示词.md",
    "配网安全与绿色施工保障措施提示词.md",
    "配网工程进度计划及保证措施提示词.md",
]
SAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "samples"
PLACEHOLDER_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")


def test_chart_prompt_docs_list_supported_chart_types() -> None:
    for filename in PROMPT_FILES:
        content = (SAMPLES_DIR / filename).read_text(encoding="utf-8")
        for chart_type in sorted(SUPPORTED_CHART_TYPES):
            assert f"`{chart_type}`" in content, filename
        assert "未列入支持类型的图表，一律用 Markdown 表格表达" in content


def test_chart_prompt_placeholders_use_supported_chart_types() -> None:
    allowed = set(SUPPORTED_CHART_TYPES)
    for path in SAMPLES_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        placeholders = set(PLACEHOLDER_RE.findall(content))
        assert placeholders <= allowed, f"{path.name}: {sorted(placeholders - allowed)}"
