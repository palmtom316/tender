from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ASSET_TYPE_KEYS = ("vehicle", "machine", "tool", "safety")
OWNERSHIP_VALUES = ("self", "leased", "third_party")
STATUS_VALUES = ("active", "maintenance", "retired")


@dataclass(frozen=True)
class AssetCommonFields:
    asset_type: str
    name: str
    unit: str
    ownership: str
    quantity: float
    status: str
    extras: dict[str, Any]


def validate_common_fields(fields: dict[str, Any]) -> AssetCommonFields:
    asset_type = str(fields.get("asset_type") or "").strip()
    name = str(fields.get("name") or "").strip()
    unit = str(fields.get("unit") or "").strip()
    ownership = str(fields.get("ownership") or "").strip()
    status = str(fields.get("status") or "active").strip() or "active"
    quantity = fields.get("quantity", 1)
    extras = fields.get("extras") or {}

    if asset_type not in ASSET_TYPE_KEYS:
        raise ValueError("asset_type is invalid")
    if not name:
        raise ValueError("name is required")
    if not unit:
        raise ValueError("unit is required")
    if ownership not in OWNERSHIP_VALUES:
        raise ValueError("ownership is invalid")
    if status not in STATUS_VALUES:
        raise ValueError("status is invalid")
    try:
        quantity_value = float(quantity)
    except (TypeError, ValueError) as exc:
        raise ValueError("quantity must be numeric") from exc
    if quantity_value <= 0:
        raise ValueError("quantity must be greater than 0")
    if not isinstance(extras, dict):
        raise ValueError("extras must be a JSON object")

    return AssetCommonFields(
        asset_type=asset_type,
        name=name,
        unit=unit,
        ownership=ownership,
        quantity=quantity_value,
        status=status,
        extras=extras,
    )
