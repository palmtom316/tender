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
FLASH_MIGRATION_FILE = (
    BACKEND_ROOT
    / "tender_backend"
    / "db"
    / "alembic"
    / "versions"
    / "0015_deepseek_v4_flash_defaults.py"
)


def test_tag_clauses_seed_defaults_to_deepseek_v4_flash() -> None:
    content = MIGRATION_FILE.read_text(encoding="utf-8")

    match = re.search(
        r"\(gen_random_uuid\(\),\s*'tag_clauses'.*?'(https://[^']+)'\s*,\s*'([^']+)'\s*,\s*'(https://[^']+)'\s*,\s*'([^']+)'\)",
        content,
        re.DOTALL,
    )

    assert match is not None
    assert match.group(1) == "https://api.deepseek.com/v1"
    assert match.group(2) == "deepseek-v4-flash"
    assert match.group(3) == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert match.group(4) == "qwen-plus"


def test_tag_clauses_normalization_migration_updates_legacy_primary_route() -> None:
    content = NORMALIZE_MIGRATION_FILE.read_text(encoding="utf-8")

    assert "SET base_url = 'https://api.siliconflow.cn/v1'" in content
    assert "primary_model = 'deepseek-ai/DeepSeek-V3.2'" in content
    assert "WHERE agent_key = 'tag_clauses'" in content
    assert "base_url = 'https://api.deepseek.com/v1'" in content
    assert "primary_model = 'deepseek-chat'" in content


def test_flash_migration_updates_legacy_deepseek_models_without_v4_pro() -> None:
    content = FLASH_MIGRATION_FILE.read_text(encoding="utf-8")

    assert "primary_model = 'deepseek-v4-flash'" in content
    assert "deepseek-v4-pro" not in content.lower()
    assert "deepseek-chat" in content
    assert "deepseek-reasoner" in content
    assert "deepseek-ai/DeepSeek-V3.2" in content
