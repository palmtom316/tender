"""Multi-factor bid template package selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection

from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository, BidTemplatePackageRow
from tender_backend.db.repositories.project_repository import ProjectRepository


@dataclass(frozen=True)
class TemplateCandidate:
    package_id: UUID
    package_key: str
    display_name: str
    package_type: str
    category_code: str | None
    score: int
    reasons: list[str]
    warnings: list[str]


class TemplateSelectionService:
    def __init__(
        self,
        *,
        project_repo: ProjectRepository | None = None,
        template_repo: BidTemplatePackageRepository | None = None,
    ) -> None:
        self.project_repo = project_repo or ProjectRepository()
        self.template_repo = template_repo or BidTemplatePackageRepository()

    def preview(self, conn: Connection, *, project_id: UUID) -> dict[str, Any]:
        project = self.project_repo.get(conn, project_id=project_id)
        if project is None:
            raise ValueError("project not found")
        packages = self.template_repo.list_all(conn)
        candidates = [self._score(project.__dict__, package) for package in packages]
        candidates.sort(key=lambda item: (-item.score, item.display_name))
        recommended = candidates[0] if candidates and candidates[0].score > 0 else None
        return {
            "project_id": str(project_id),
            "recommended": asdict(recommended) if recommended else None,
            "candidates": [asdict(candidate) for candidate in candidates],
        }

    def confirm(self, conn: Connection, *, project_id: UUID, package_id: UUID) -> dict[str, Any]:
        package = self.template_repo.get_by_id(conn, package_id=package_id)
        if package is None:
            raise ValueError("template package not found")
        project = self.project_repo.update(
            conn,
            project_id=project_id,
            fields={"selected_template_package_id": package_id},
        )
        if project is None:
            raise ValueError("project not found")
        return {"project_id": str(project_id), "selected_template_package_id": str(package_id)}

    def _score(self, project: dict[str, Any], package: BidTemplatePackageRow) -> TemplateCandidate:
        manifest = dict(package.source_manifest or {})
        metadata = dict(manifest.get("metadata") or {})
        tags = {str(item).lower() for item in metadata.get("tags") or manifest.get("tags") or []}
        package_blob = " ".join(
            str(value).lower()
            for value in [package.package_key, package.display_name, package.package_type, package.category_code, *tags]
            if value
        )
        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        factors = [
            ("business_line", 40),
            ("sub_type", 30),
            ("employer_type", 16),
            ("evaluation_method", 12),
            ("qualification_review_type", 12),
            ("tender_platform", 10),
        ]
        if str(project.get("industry") or "power").lower() in package_blob or "power" in package_blob or "电" in package.display_name:
            score += 20
            reasons.append("industry matched")
        for key, weight in factors:
            value = project.get(key)
            if not value:
                continue
            if str(value).lower() in package_blob or str(value) in package.display_name:
                score += weight
                reasons.append(f"{key} matched")
            else:
                warnings.append(f"{key} not matched")
        voltage = project.get("voltage_level") or []
        for level in voltage:
            if str(level).lower() in package_blob:
                score += 18
                reasons.append("voltage_level matched")
                break
        if package.package_type in {project.get("project_type"), project.get("business_line"), project.get("sub_type")}:
            score += 24
            reasons.append("package_type matched")
        if not reasons:
            warnings.append("no strong metadata match")
        return TemplateCandidate(
            package_id=package.id,
            package_key=package.package_key,
            display_name=package.display_name,
            package_type=package.package_type,
            category_code=package.category_code,
            score=score,
            reasons=reasons,
            warnings=warnings,
        )


__all__ = ["TemplateSelectionService", "TemplateCandidate"]
