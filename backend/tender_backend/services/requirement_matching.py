"""Rule-based matching between tender requirements and company master data."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection

from tender_backend.db.repositories.master_data_repo import MasterDataRepository
from tender_backend.db.repositories.requirement_match_repo import RequirementMatchRepository
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.db.repositories.standard_repo import StandardRepository


MATCH_STATUSES = {"satisfied", "likely_satisfied", "missing", "needs_review"}


def _normalize_record(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    return dict(value)


def _text(row: dict[str, Any]) -> str:
    return " ".join(str(value) for value in row.values() if value not in {None, ""}).casefold()


def _requirement_text(requirement: dict[str, Any]) -> str:
    return " ".join(
        str(requirement.get(key) or "")
        for key in ("title", "requirement_text", "source_text")
    ).casefold()


def _tokens(value: str) -> set[str]:
    raw = value.replace("，", " ").replace("。", " ").replace("；", " ").replace(",", " ").replace(";", " ")
    tokens = {token.strip().casefold() for token in raw.split() if len(token.strip()) >= 2}
    compact = "".join(raw.split()).casefold()
    if compact and any("\u4e00" <= ch <= "\u9fff" for ch in compact):
        tokens.update(compact[index:index + 2] for index in range(max(0, len(compact) - 1)))
    return tokens


def _score(requirement_text: str, record_text: str) -> float:
    tokens = _tokens(requirement_text)
    if not tokens:
        return 0.45 if requirement_text and requirement_text in record_text else 0.0
    hits = sum(1 for token in tokens if token in record_text)
    return hits / len(tokens)


def _match_records(
    *,
    requirement: dict[str, Any],
    records: list[dict[str, Any]],
    source_type: str,
    title_keys: tuple[str, ...],
    missing_reason: str,
) -> dict[str, Any]:
    req_text = _requirement_text(requirement)
    scored: list[tuple[float, dict[str, Any]]] = [
        (_score(req_text, _text(record)), record)
        for record in records
    ]
    scored.sort(key=lambda item: item[0], reverse=True)

    if not scored:
        return {
            "requirement_id": requirement["id"],
            "match_status": "missing",
            "missing_reason": missing_reason,
            "requires_human_confirm": True,
            "metadata_json": {"matched_source_type": source_type},
        }

    score, record = scored[0]
    if score >= 0.35:
        status = "satisfied"
    elif score > 0:
        status = "likely_satisfied"
    else:
        status = "needs_review"

    title = next((str(record.get(key)) for key in title_keys if record.get(key)), source_type)
    return {
        "requirement_id": requirement["id"],
        "match_status": status,
        "matched_source_type": source_type,
        "matched_source_id": record.get("id"),
        "matched_title": title,
        "match_score": round(score, 4),
        "evidence_summary": title if status in {"satisfied", "likely_satisfied"} else None,
        "missing_reason": None if status in {"satisfied", "likely_satisfied"} else "未找到明确匹配资料，需人工复核",
        "requires_human_confirm": status != "satisfied",
        "metadata_json": {"candidate_count": len(records)},
    }


def _match_standard_clauses(requirement: dict[str, Any], clauses: list[dict[str, Any]]) -> dict[str, Any]:
    return _match_records(
        requirement=requirement,
        records=clauses,
        source_type="standard_clause",
        title_keys=("clause_title", "standard_name", "clause_no"),
        missing_reason="未找到可支撑该技术/验收要求的标准规范条款",
    )


def build_requirement_matches(conn: Connection, *, project_id: UUID) -> dict[str, Any]:
    requirement_repo = RequirementRepository()
    match_repo = RequirementMatchRepository()
    master_repo = MasterDataRepository()
    standard_repo = StandardRepository()

    requirements = [
        row for row in requirement_repo.list_by_project(conn, project_id=project_id)
        if not row.get("ignored_for_pricing") and row.get("review_status") != "rejected"
    ]
    certificates = [_normalize_record(row) for row in master_repo.list_certificates(conn)]
    performances = [_normalize_record(row) for row in master_repo.list_project_performances(conn)]
    people = [_normalize_record(row) for row in master_repo.list_people(conn)]
    companies = [_normalize_record(row) for row in master_repo.list_company_profiles(conn)]
    evidence_assets = [_normalize_record(row) for row in master_repo.list_evidence_assets(conn)]

    matches: list[dict[str, Any]] = []
    for requirement in requirements:
        category = requirement.get("category")
        req_text = _requirement_text(requirement)
        if category == "qualification":
            matches.append(
                _match_records(
                    requirement=requirement,
                    records=certificates,
                    source_type="qualification_certificate",
                    title_keys=("certificate_name", "certificate_no", "specialty", "grade"),
                    missing_reason="未找到可证明该资格要求的资质/认证/许可资料",
                )
            )
        elif category == "performance":
            matches.append(
                _match_records(
                    requirement=requirement,
                    records=performances,
                    source_type="project_performance",
                    title_keys=("project_name", "client_name", "service_scope"),
                    missing_reason="未找到可证明该业绩要求的企业业绩资料",
                )
            )
        elif category == "project_team":
            person_match = _match_records(
                requirement=requirement,
                records=people,
                source_type="person_profile",
                title_keys=("full_name", "role_name", "title", "specialty"),
                missing_reason="未找到可证明该项目团队要求的人员资料",
            )
            matches.append(person_match)
            if any(keyword in req_text for keyword in ("社保", "任职", "劳动合同", "在职")):
                matches.append(
                    _match_records(
                        requirement=requirement,
                        records=[
                            row
                            for row in evidence_assets
                            if str(row.get("asset_category") or row.get("asset_name") or "").find("社保") >= 0
                            or str(row.get("asset_category") or row.get("asset_name") or "").find("任职") >= 0
                            or str(row.get("asset_category") or row.get("asset_name") or "").find("劳动合同") >= 0
                        ],
                        source_type="person_evidence_asset",
                        title_keys=("asset_name", "file_name", "asset_category"),
                        missing_reason="未找到可证明人员社保/任职关系的附件资料",
                    )
                )
        elif category in {"project_info", "business"}:
            matches.append(
                _match_records(
                    requirement=requirement,
                    records=companies,
                    source_type="company_profile",
                    title_keys=("company_name", "company_code", "business_scope"),
                    missing_reason="未找到可响应该要求的企业基础资料",
                )
            )
        elif category in {"technical", "contract"} or "验收" in req_text or "标准" in req_text:
            clauses = [_normalize_record(row) for row in standard_repo.list_matching_clauses(conn, query=req_text, limit=50)]
            matches.append(_match_standard_clauses(requirement, clauses))
    persisted = match_repo.replace_for_project(conn, project_id=project_id, matches=matches)
    missing = [row for row in persisted if row["match_status"] == "missing"]
    needs_review = [row for row in persisted if row["match_status"] in {"likely_satisfied", "needs_review"} or row["requires_human_confirm"]]
    return {
        "project_id": str(project_id),
        "match_count": len(persisted),
        "missing_count": len(missing),
        "needs_review_count": len(needs_review),
        "matches": persisted,
        "missing_items": missing,
        "needs_review_items": needs_review,
    }
