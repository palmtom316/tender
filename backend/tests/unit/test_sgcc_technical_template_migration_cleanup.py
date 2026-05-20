from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "tender_backend"
    / "db"
    / "alembic"
    / "versions"
    / "0061_sync_sgcc_distribution_technical_template.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0061", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0061_syncs_desired_technical_template_and_removes_legacy_0045_rows() -> None:
    module = _load_migration()

    desired_codes = {code for code, _title in module._ITEMS}
    legacy_codes = {"5.4", "14", "14.1", "15", "16"}

    assert legacy_codes.isdisjoint(desired_codes)
    assert {"0", "0.1", "0.2", "0.3", "11", "12", "13"} <= desired_codes
    assert "DELETE FROM bid_template_item" in module._cleanup_sql()
    assert "item_code NOT IN" in module._cleanup_sql()
    assert "sgcc_distribution_technical_v1" in module._cleanup_sql()


def test_0061_upgrade_upserts_before_cleanup(monkeypatch) -> None:
    module = _load_migration()
    executed: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda sql: executed.append(str(sql)))

    module.upgrade()

    assert len(executed) == 2
    assert "INSERT INTO bid_template_item" in executed[0]
    assert "ON CONFLICT" in executed[0]
    assert "DELETE FROM bid_template_item" in executed[1]
