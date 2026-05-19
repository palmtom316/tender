from __future__ import annotations

import pytest
from pydantic import ValidationError

from tender_backend.api.deviation_table import (
    DeviationTableBody,
    _deviation_data_for_volume,
    _store_deviation_data_for_volume,
)


def test_deviation_table_body_accepts_business_and_technical_volume_type() -> None:
    assert DeviationTableBody(volume_type="business").volume_type == "business"
    assert DeviationTableBody(volume_type="technical").volume_type == "technical"


def test_deviation_table_body_rejects_unknown_volume_type() -> None:
    with pytest.raises(ValidationError):
        DeviationTableBody(volume_type="qualification")


def test_deviation_table_metadata_is_separated_by_volume_type() -> None:
    metadata: dict = {}
    business = {"volume_type": "business", "has_deviation": False, "items": []}
    technical = {"volume_type": "technical", "has_deviation": True, "items": [{"seq_number": 1}]}

    _store_deviation_data_for_volume(metadata, "business", business)
    _store_deviation_data_for_volume(metadata, "technical", technical)

    assert _deviation_data_for_volume(metadata, "business") == business
    assert _deviation_data_for_volume(metadata, "technical") == technical
    assert metadata["deviation_table"] == technical
