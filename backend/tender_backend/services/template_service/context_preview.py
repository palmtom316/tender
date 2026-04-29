from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg import Connection

from tender_backend.db.repositories.bid_template_binding_repo import BidTemplateBindingRepository
from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository
from tender_backend.db.repositories.master_data_repo import MasterDataRepository


_VALID_SOURCE_TYPES = {
    "company_profile",
    "person_profile",
    "project_performance",
    "qualification_certificate",
    "financial_statement",
}
_VALID_SELECTION_MODES = {"all", "latest", "first", "by_id"}


def validate_source_type(value: str) -> str:
    if value not in _VALID_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type: {value}")
    return value


def validate_selection_mode(value: str) -> str:
    if value not in _VALID_SELECTION_MODES:
        raise ValueError(f"Unsupported selection_mode: {value}")
    return value


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if is_dataclass(value):
        return {key: _normalize_value(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _normalize_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _matches_filters(record: dict[str, Any], filters: dict[str, Any]) -> bool:
    if not filters:
        return True
    equals = filters.get("equals")
    if isinstance(equals, dict):
        for key, expected in equals.items():
            if record.get(key) != expected:
                return False
    contains = filters.get("contains")
    if isinstance(contains, dict):
        for key, expected in contains.items():
            value = record.get(key)
            if value is None or str(expected) not in str(value):
                return False
    ids = filters.get("record_ids")
    if isinstance(ids, list) and ids:
        normalized_ids = {str(item) for item in ids}
        if str(record.get("id")) not in normalized_ids:
            return False
    return True


def _select_records(records: list[dict[str, Any]], selection_mode: str) -> Any:
    if selection_mode == "all":
        return records
    if not records:
        return None if selection_mode in {"latest", "first", "by_id"} else records
    if selection_mode == "first":
        return records[0]
    if selection_mode == "latest":
        return records[0]
    if selection_mode == "by_id":
        return records[0]
    return records


def _load_source_rows(conn: Connection, *, source_type: str) -> list[dict[str, Any]]:
    repo = MasterDataRepository()
    if source_type == "company_profile":
        rows = repo.list_company_profiles(conn)
    elif source_type == "person_profile":
        rows = repo.list_people(conn)
    elif source_type == "project_performance":
        rows = repo.list_project_performances(conn)
    elif source_type == "qualification_certificate":
        rows = repo.list_certificates(conn)
    elif source_type == "financial_statement":
        rows = repo.list_financial_statements(conn)
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")
    return [_normalize_value(row) for row in rows]


def build_package_context_preview(conn: Connection, *, package_id: UUID) -> dict[str, Any]:
    package_repo = BidTemplatePackageRepository()
    binding_repo = BidTemplateBindingRepository()

    package = package_repo.get_by_id(conn, package_id=package_id)
    if package is None:
        raise LookupError("template package not found")

    items = package_repo.list_items(conn, package_id=package_id)
    bindings = binding_repo.list_by_package(conn, package_id=package_id)
    bindings_by_item: dict[UUID, list] = {}
    for binding in bindings:
        bindings_by_item.setdefault(binding.template_item_id, []).append(binding)

    source_cache: dict[str, list[dict[str, Any]]] = {}
    item_previews: list[dict[str, Any]] = []
    for item in items:
        item_bindings = bindings_by_item.get(item.id, [])
        resolved_bindings: list[dict[str, Any]] = []
        for binding in item_bindings:
            source_type = validate_source_type(binding.source_type)
            selection_mode = validate_selection_mode(binding.selection_mode)
            if source_type not in source_cache:
                source_cache[source_type] = _load_source_rows(conn, source_type=source_type)
            filtered = [
                record for record in source_cache[source_type]
                if _matches_filters(record, binding.source_filters)
            ]
            resolved_bindings.append({
                "binding_id": str(binding.id),
                "binding_name": binding.binding_name,
                "source_type": source_type,
                "selection_mode": selection_mode,
                "output_key": binding.output_key,
                "required": binding.required,
                "filters": binding.source_filters,
                "matched_count": len(filtered),
                "data": _select_records(filtered, selection_mode),
            })
        item_previews.append({
            "item_id": str(item.id),
            "item_code": item.item_code,
            "item_name": item.item_name,
            "filename": item.filename,
            "binding_count": len(item_bindings),
            "bindings": resolved_bindings,
        })

    return {
        "package_id": str(package.id),
        "package_key": package.package_key,
        "display_name": package.display_name,
        "package_type": package.package_type,
        "items": item_previews,
    }
