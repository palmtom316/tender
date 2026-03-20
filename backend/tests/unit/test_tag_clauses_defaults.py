from __future__ import annotations

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_FILE = BACKEND_ROOT / "tender_backend" / "db" / "alembic" / "versions" / "0004_agent_config.py"


def test_tag_clauses_seed_defaults_to_deepseek_primary_and_siliconflow_fallback() -> None:
    content = MIGRATION_FILE.read_text(encoding="utf-8")

    assert "'tag_clauses'" in content
    assert "'https://api.deepseek.com/v1'" in content
    assert "'deepseek-chat'" in content
    assert "'https://api.siliconflow.cn/v1'" in content
    assert "'deepseek-ai/DeepSeek-V3.2'" in content
