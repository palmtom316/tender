from __future__ import annotations

import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_FILE = BACKEND_ROOT / "tender_backend" / "db" / "alembic" / "versions" / "0004_agent_config.py"
NORMALIZE_MIGRATION_FILE = (
    BACKEND_ROOT
    / "tender_backend"
    / "db"
    / "alembic"
    / "versions"
    / "0009_tag_clauses_siliconflow_primary.py"
)


def test_tag_clauses_seed_defaults_to_siliconflow_primary() -> None:
    content = MIGRATION_FILE.read_text(encoding="utf-8")

    match = re.search(
        r"\(gen_random_uuid\(\),\s*'tag_clauses'.*?'(https://[^']+)'\s*,\s*'([^']+)'\s*,\s*'(https://[^']+)'\s*,\s*'([^']+)'\)",
        content,
        re.DOTALL,
    )

    assert match is not None
    assert match.group(1) == "https://api.siliconflow.cn/v1"
    assert match.group(2) == "deepseek-ai/DeepSeek-V3.2"
    assert match.group(3) == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert match.group(4) == "qwen-plus"


def test_tag_clauses_normalization_migration_updates_legacy_primary_route() -> None:
    content = NORMALIZE_MIGRATION_FILE.read_text(encoding="utf-8")

    assert "SET base_url = 'https://api.siliconflow.cn/v1'" in content
    assert "primary_model = 'deepseek-ai/DeepSeek-V3.2'" in content
    assert "WHERE agent_key = 'tag_clauses'" in content
    assert "base_url = 'https://api.deepseek.com/v1'" in content
    assert "primary_model = 'deepseek-chat'" in content
