from __future__ import annotations

from tender_backend.core.config import Settings


def test_vl_repair_defaults_favor_reliability_over_parallelism() -> None:
    settings = Settings()

    assert settings.vl_repair_max_concurrent_tasks == 1
    assert settings.vl_repair_ai_gateway_timeout_seconds == 300.0
