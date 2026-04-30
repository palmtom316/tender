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
from tender_backend.services.tender_requirement_priority import (
    apply_tender_requirement_context,
    load_tender_requirement_overrides,
)


_VALID_SOURCE_TYPES = {
    "company_profile",
    "person_profile",
    "project_performance",
    "qualification_certificate",
    "financial_statement",
    "evidence_asset",
}
_VALID_SELECTION_MODES = {"all", "latest", "first", "by_id"}
_VALID_FIELD_MAPPING_MODES = {"augment", "replace"}
_VALID_FIELD_MAPPING_TRANSFORMS = {"copy", "join", "date", "number"}


def validate_source_type(value: str) -> str:
    if value not in _VALID_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type: {value}")
    return value


def validate_selection_mode(value: str) -> str:
    if value not in _VALID_SELECTION_MODES:
        raise ValueError(f"Unsupported selection_mode: {value}")
    return value


def validate_field_mapping_mode(value: str) -> str:
    if value not in _VALID_FIELD_MAPPING_MODES:
        raise ValueError(f"Unsupported field_mapping_mode: {value}")
    return value


def validate_field_mappings(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError("field_mappings must contain objects")
        target_field = str(mapping.get("target_field") or "").strip()
        if not target_field:
            raise ValueError("field_mappings.target_field is required")
        transform = str(mapping.get("transform") or "copy")
        if transform not in _VALID_FIELD_MAPPING_TRANSFORMS:
            raise ValueError(f"Unsupported field_mapping transform: {transform}")
        source_field = str(mapping.get("source_field") or "").strip()
        source_fields = mapping.get("source_fields")
        if transform == "join":
            if not isinstance(source_fields, list) or not source_fields:
                raise ValueError("join field mapping requires source_fields")
        elif not source_field:
            raise ValueError("field mapping requires source_field")
    return mappings


def suggest_field_mappings(*, item_name: str, item_code: str | None, source_type: str) -> list[dict[str, Any]]:
    validate_source_type(source_type)
    mappings: list[dict[str, Any]] = []

    if source_type == "company_profile" and ("基本情况表" in item_name or (item_code or "").startswith("5")):
        mappings.extend(
            [
                {"target_field": "company_title", "source_field": "company_name"},
                {"target_field": "credit_code", "source_field": "unified_social_credit_code"},
                {"target_field": "address_text", "source_field": "registered_address"},
                {"target_field": "contact_summary", "source_fields": ["contact_name", "contact_phone"], "transform": "join", "join_with": " / "},
            ]
        )
    elif source_type == "person_profile" and ("人员" in item_name or "团队" in item_name or (item_code or "").startswith("6")):
        mappings.extend(
            [
                {"target_field": "person_name", "source_field": "full_name"},
                {"target_field": "role_label", "source_field": "role_name"},
                {"target_field": "title_label", "source_field": "title"},
                {"target_field": "specialty_label", "source_field": "specialty"},
                {"target_field": "experience_years_text", "source_field": "years_experience", "transform": "number", "decimals": 0},
                {"target_field": "contact_summary", "source_fields": ["phone", "email"], "transform": "join", "join_with": " / "},
            ]
        )
    elif source_type == "project_performance" and ("业绩" in item_name or (item_code or "").startswith("5")):
        mappings.extend(
            [
                {"target_field": "project_title", "source_field": "project_name"},
                {"target_field": "client_title", "source_field": "client_name"},
                {"target_field": "contract_amount_text", "source_field": "contract_amount", "transform": "number", "decimals": 2},
                {"target_field": "started_on_text", "source_field": "started_on", "transform": "date", "date_format": "%Y-%m-%d"},
                {"target_field": "ended_on_text", "source_field": "ended_on", "transform": "date", "date_format": "%Y-%m-%d"},
                {"target_field": "contact_summary", "source_fields": ["contact_name", "contact_phone"], "transform": "join", "join_with": " / "},
            ]
        )
    elif source_type == "qualification_certificate" and ("证书" in item_name or "认证" in item_name):
        mappings.extend(
            [
                {"target_field": "certificate_title", "source_field": "certificate_name"},
                {"target_field": "certificate_code", "source_field": "certificate_no"},
                {"target_field": "holder_title", "source_field": "holder_name"},
                {"target_field": "valid_to_text", "source_field": "valid_to", "transform": "date", "date_format": "%Y-%m-%d"},
            ]
        )
    elif source_type == "financial_statement" and ("财务" in item_name or (item_code or "").startswith("8")):
        mappings.extend(
            [
                {"target_field": "fiscal_year_label", "source_field": "fiscal_year", "transform": "number", "decimals": 0},
                {"target_field": "statement_title", "source_field": "statement_type"},
                {"target_field": "source_note_text", "source_field": "source_note"},
            ]
        )
    elif source_type == "evidence_asset":
        mappings.extend(
            [
                {"target_field": "asset_title", "source_field": "asset_name"},
                {"target_field": "file_title", "source_field": "file_name"},
            ]
        )

    return mappings


def _suggest_field_mapping_group(
    *,
    item_name: str,
    item_code: str | None,
    source_type: str,
) -> dict[str, Any]:
    mappings = suggest_field_mappings(item_name=item_name, item_code=item_code, source_type=source_type)
    confidence = 0.15

    if source_type == "company_profile" and ("基本情况表" in item_name or (item_code or "").startswith("5")):
        confidence = 0.85
    elif source_type == "person_profile" and ("人员" in item_name or "团队" in item_name or (item_code or "").startswith("6")):
        confidence = 0.82
    elif source_type == "project_performance" and ("业绩" in item_name or (item_code or "").startswith("5")):
        confidence = 0.8
    elif source_type == "qualification_certificate" and ("证书" in item_name or "认证" in item_name):
        confidence = 0.83
    elif source_type == "financial_statement" and ("财务" in item_name or (item_code or "").startswith("8")):
        confidence = 0.76
    elif source_type == "evidence_asset":
        confidence = 0.55
    elif mappings:
        confidence = 0.4

    return {
        "source_type": source_type,
        "field_mapping_mode": "augment",
        "field_mappings": mappings,
        "confidence": confidence,
    }


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


def _latest_sort_key(record: dict[str, Any], *, source_type: str) -> tuple[Any, ...]:
    if source_type == "company_profile":
        return (
            record.get("updated_at") or "",
            record.get("created_at") or "",
            str(record.get("id") or ""),
        )
    if source_type == "person_profile":
        return (
            record.get("updated_at") or "",
            record.get("created_at") or "",
            str(record.get("id") or ""),
        )
    if source_type == "project_performance":
        return (
            record.get("ended_on") or "",
            record.get("started_on") or "",
            record.get("updated_at") or "",
            record.get("created_at") or "",
            str(record.get("id") or ""),
        )
    if source_type == "qualification_certificate":
        return (
            record.get("valid_to") or "",
            record.get("valid_from") or "",
            record.get("updated_at") or "",
            record.get("created_at") or "",
            str(record.get("id") or ""),
        )
    if source_type == "financial_statement":
        return (
            record.get("fiscal_year") or -1,
            record.get("updated_at") or "",
            record.get("created_at") or "",
            str(record.get("id") or ""),
        )
    if source_type == "evidence_asset":
        return (
            record.get("issued_on") or "",
            record.get("expires_on") or "",
            record.get("updated_at") or "",
            record.get("created_at") or "",
            record.get("sort_order") or -1,
            str(record.get("id") or ""),
        )
    return (
        record.get("updated_at") or "",
        record.get("created_at") or "",
        str(record.get("id") or ""),
    )


def _select_records(
    records: list[dict[str, Any]],
    selection_mode: str,
    *,
    source_type: str | None = None,
    filters: dict[str, Any] | None = None,
) -> Any:
    if selection_mode == "all":
        return records
    if not records:
        return None if selection_mode in {"latest", "first", "by_id"} else records
    if selection_mode == "first":
        return records[0]
    if selection_mode == "latest":
        return max(records, key=lambda record: _latest_sort_key(record, source_type=source_type or ""))
    if selection_mode == "by_id":
        record_ids = (filters or {}).get("record_ids")
        if not isinstance(record_ids, list) or not record_ids:
            raise ValueError("selection_mode 'by_id' requires source_filters.record_ids")
        by_id = {str(record.get("id")): record for record in records}
        for record_id in record_ids:
            selected = by_id.get(str(record_id))
            if selected is not None:
                return selected
        return None
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
    elif source_type == "evidence_asset":
        rows = repo.list_evidence_assets(conn)
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")
    return [_normalize_value(row) for row in rows]


def _get_nested_value(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _coerce_date_text(value: Any, output_format: str | None) -> Any:
    if value in {None, ""}:
        return value
    raw = str(value)
    normalized = raw.split("T", 1)[0]
    if output_format in {None, "", "%Y-%m-%d"}:
        return normalized
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{normalized}T00:00:00")
        except ValueError:
            return normalized
    return parsed.strftime(output_format)


def _coerce_number_text(value: Any, decimals: int | None) -> Any:
    if value in {None, ""}:
        return value
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value))
        except ValueError:
            return value
    if decimals is None:
        if number.is_integer():
            return str(int(number))
        return str(number)
    return f"{number:.{decimals}f}"


def _apply_field_mapping_to_record(
    record: dict[str, Any],
    mappings: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    base = {} if mode == "replace" else dict(record)
    for mapping in mappings:
        target_field = str(mapping["target_field"]).strip()
        transform = str(mapping.get("transform") or "copy")
        default_value = mapping.get("default_value")
        if transform == "join":
            raw_fields = mapping.get("source_fields") or []
            values = [
                _get_nested_value(record, str(field))
                for field in raw_fields
            ]
            join_with = str(mapping.get("join_with") or "")
            non_empty = [str(value) for value in values if value not in {None, ""}]
            value = join_with.join(non_empty)
        else:
            value = _get_nested_value(record, str(mapping.get("source_field") or ""))
            if transform == "date":
                value = _coerce_date_text(value, mapping.get("date_format"))
            elif transform == "number":
                decimals = mapping.get("decimals")
                value = _coerce_number_text(value, decimals if isinstance(decimals, int) else None)
        if value in {None, ""} and "default_value" in mapping:
            value = default_value
        base[target_field] = value
    return base


def _apply_field_mappings(
    data: Any,
    mappings: list[dict[str, Any]],
    *,
    mode: str,
) -> Any:
    if not mappings:
        return data
    if isinstance(data, dict):
        return _apply_field_mapping_to_record(data, mappings, mode=mode)
    if isinstance(data, list):
        return [
            _apply_field_mapping_to_record(item, mappings, mode=mode)
            if isinstance(item, dict) else item
            for item in data
        ]
    return data


def _resolve_binding_payloads(
    conn: Connection,
    *,
    bindings: list,
    source_cache: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    cache = source_cache if source_cache is not None else {}
    resolved_bindings: list[dict[str, Any]] = []
    for binding in bindings:
        source_type = validate_source_type(binding.source_type)
        selection_mode = validate_selection_mode(binding.selection_mode)
        field_mapping_mode = validate_field_mapping_mode(binding.field_mapping_mode)
        field_mappings = validate_field_mappings(binding.field_mappings)
        if source_type not in cache:
            cache[source_type] = _load_source_rows(conn, source_type=source_type)
        filtered = [
            record for record in cache[source_type]
            if _matches_filters(record, binding.source_filters)
        ]
        selected = _select_records(filtered, selection_mode, source_type=source_type, filters=binding.source_filters)
        mapped = _apply_field_mappings(selected, field_mappings, mode=field_mapping_mode)
        resolved_bindings.append({
            "binding_id": str(binding.id),
            "binding_name": binding.binding_name,
            "source_type": source_type,
            "selection_mode": selection_mode,
            "field_mappings": field_mappings,
            "field_mapping_mode": field_mapping_mode,
            "output_key": binding.output_key,
            "required": binding.required,
            "filters": binding.source_filters,
            "matched_count": len(filtered),
            "data": mapped,
        })
    return resolved_bindings


def _build_render_context_from_bindings(bindings: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    context: dict[str, Any] = {}
    missing_required: list[str] = []
    for binding in bindings:
        context[binding["output_key"]] = binding["data"]
        if binding["required"]:
            data = binding["data"]
            if data is None or data == []:
                missing_required.append(binding["binding_name"])
    return context, missing_required


def _apply_project_requirement_overrides(
    conn: Connection,
    *,
    context: dict[str, Any],
    project_id: UUID | None = None,
) -> dict[str, Any]:
    if project_id is None:
        return context
    overrides = load_tender_requirement_overrides(conn, project_id=project_id)
    return apply_tender_requirement_context(context, overrides)


def build_item_render_context(conn: Connection, *, item_id: UUID, project_id: UUID | None = None) -> dict[str, Any]:
    package_repo = BidTemplatePackageRepository()
    binding_repo = BidTemplateBindingRepository()

    item = package_repo.get_item_by_id(conn, item_id=item_id)
    if item is None:
        raise LookupError("template item not found")

    bindings = binding_repo.list_by_item(conn, template_item_id=item.id)
    resolved = _resolve_binding_payloads(conn, bindings=bindings)
    context, missing_required = _build_render_context_from_bindings(resolved)
    context = _apply_project_requirement_overrides(conn, context=context, project_id=project_id)
    return {
        "item_id": str(item.id),
        "item_code": item.item_code,
        "item_name": item.item_name,
        "filename": item.filename,
        "render_mode": item.render_mode,
        "binding_count": len(resolved),
        "ready": len(missing_required) == 0,
        "missing_required_bindings": missing_required,
        "context": context,
        "bindings": resolved,
    }


def build_package_render_context(conn: Connection, *, package_id: UUID, project_id: UUID | None = None) -> dict[str, Any]:
    package_repo = BidTemplatePackageRepository()
    binding_repo = BidTemplateBindingRepository()

    package = package_repo.get_by_id(conn, package_id=package_id)
    if package is None:
        raise LookupError("template package not found")

    items = package_repo.list_items(conn, package_id=package_id)
    all_bindings = binding_repo.list_by_package(conn, package_id=package_id)
    bindings_by_item: dict[UUID, list] = {}
    for binding in all_bindings:
        bindings_by_item.setdefault(binding.template_item_id, []).append(binding)

    source_cache: dict[str, list[dict[str, Any]]] = {}
    item_contexts: list[dict[str, Any]] = []
    for item in items:
        resolved = _resolve_binding_payloads(
            conn,
            bindings=bindings_by_item.get(item.id, []),
            source_cache=source_cache,
        )
        context, missing_required = _build_render_context_from_bindings(resolved)
        context = _apply_project_requirement_overrides(conn, context=context, project_id=project_id)
        item_contexts.append({
            "item_id": str(item.id),
            "item_code": item.item_code,
            "item_name": item.item_name,
            "filename": item.filename,
            "render_mode": item.render_mode,
            "binding_count": len(resolved),
            "ready": len(missing_required) == 0,
            "missing_required_bindings": missing_required,
            "context": context,
            "bindings": resolved,
        })

    return {
        "package_id": str(package.id),
        "package_key": package.package_key,
        "display_name": package.display_name,
        "package_type": package.package_type,
        "ready_item_count": sum(1 for item in item_contexts if item["ready"]),
        "total_item_count": len(item_contexts),
        "items": item_contexts,
    }


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
        resolved_bindings = _resolve_binding_payloads(
            conn,
            bindings=item_bindings,
            source_cache=source_cache,
        )
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


def build_item_field_mapping_suggestions(conn: Connection, *, item_id: UUID) -> dict[str, Any]:
    package_repo = BidTemplatePackageRepository()
    binding_repo = BidTemplateBindingRepository()

    item = package_repo.get_item_by_id(conn, item_id=item_id)
    if item is None:
        raise LookupError("template item not found")

    bindings = binding_repo.list_by_item(conn, template_item_id=item.id)
    source_types = [binding.source_type for binding in bindings] or sorted(_VALID_SOURCE_TYPES)
    suggestions = [
        _suggest_field_mapping_group(
            item_name=item.item_name,
            item_code=item.item_code,
            source_type=source_type,
        )
        for source_type in source_types
    ]
    return {
        "item_id": str(item.id),
        "item_code": item.item_code,
        "item_name": item.item_name,
        "suggestions": suggestions,
    }
