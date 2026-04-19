from __future__ import annotations

from tender_backend.core.config import Settings


def test_vl_repair_defaults_favor_reliability_over_parallelism() -> None:
    settings = Settings()

    assert settings.standard_mineru_model_version == "vlm"
    assert settings.standard_mineru_language == "ch"
    assert settings.standard_mineru_enable_table is True
    assert settings.standard_repair_enabled is True
    assert settings.vl_repair_max_concurrent_tasks == 1
    assert settings.vl_repair_ai_gateway_timeout_seconds == 300.0


def test_mineru_defaults_cover_current_provider_options() -> None:
    """Per revision §2.7, the MinerU surface must carry the v4 batch-API
    option set so deployments can tune OCR/formula/page-range behaviour
    without redeploying code."""
    settings = Settings()

    assert settings.standard_mineru_model_version == "vlm"
    assert settings.standard_mineru_language == "ch"
    assert settings.standard_mineru_enable_table is True
    assert settings.standard_mineru_enable_formula is False
    assert settings.standard_mineru_is_ocr is True
    assert settings.standard_mineru_page_ranges is None
    assert settings.standard_mineru_timeout_seconds == 600.0
