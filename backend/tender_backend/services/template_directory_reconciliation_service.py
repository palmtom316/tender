"""Tender directory to project template instance reconciliation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class DirectoryReconciliationSuggestion:
    id: str
    suggestion_type: str
    severity: str
    source_type: str
    skippable: bool
    required_code: str | None = None
    required_title: str | None = None
    chapter_id: UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class TemplateDirectoryReconciliationService:
    def build_suggestions(self, project_requirements: list[Any], template_chapters: list[Any]) -> list[DirectoryReconciliationSuggestion]:
        requirements = [self._requirement_dict(item) for item in project_requirements if self._is_directory_requirement(item)]
        chapters = [self._chapter_dict(item) for item in template_chapters if getattr(item, "enabled", True)]
        suggestions: list[DirectoryReconciliationSuggestion] = []
        matched_chapter_ids: set[UUID] = set()

        chapters_by_code = {chapter["code"]: chapter for chapter in chapters if chapter["code"]}
        chapters_by_source = {chapter["source_template_item_id"]: chapter for chapter in chapters if chapter.get("source_template_item_id")}

        for req in requirements:
            exact = chapters_by_code.get(req["code"])
            source_match = chapters_by_source.get(req.get("source_template_item_id")) if req.get("source_template_item_id") else None
            title_match = self._best_title_match(req, chapters)
            matched = exact or source_match or title_match
            if matched is not None:
                matched_chapter_ids.add(matched["id"])

            source_type = req.get("source_type", "tender_document")
            severity = "critical" if source_type == "tender_addendum" or req.get("mandatory") else "medium"
            skippable = not (source_type == "tender_addendum" and severity == "critical")

            if source_match is not None and source_match["code"] != req["code"]:
                suggestions.append(
                    self._suggestion(
                        "move_chapter",
                        req,
                        source_match,
                        severity=severity,
                        source_type=source_type,
                        skippable=skippable,
                        payload={
                            "from_code": source_match["code"],
                            "required_code": req["code"],
                            "required_parent_code": self._parent_code(req["code"]),
                            "source_template_item_id": str(req.get("source_template_item_id")),
                        },
                    )
                )
                continue

            if exact is not None and exact["title"].strip() != req["title"].strip():
                if title_match is not None and title_match["id"] != exact["id"] and title_match["code"] != req["code"]:
                    suggestions.append(
                        self._suggestion(
                            "reorder_chapter" if self._parent_code(title_match["code"]) == self._parent_code(req["code"]) else "move_chapter",
                            req,
                            title_match,
                            severity=severity,
                            source_type=source_type,
                            skippable=skippable,
                            payload={
                                "from_code": title_match["code"],
                                "required_code": req["code"],
                                "required_parent_code": self._parent_code(req["code"]),
                            },
                        )
                    )
                else:
                    suggestions.append(
                        self._suggestion(
                            "rename_chapter",
                            req,
                            exact,
                            severity=severity,
                            source_type=source_type,
                            skippable=skippable,
                            payload={"from_title": exact["title"], "to_title": req["title"]},
                        )
                    )
                continue

            if title_match is not None and title_match["code"] != req["code"]:
                suggestions.append(
                    self._suggestion(
                        "reorder_chapter" if self._parent_code(title_match["code"]) == self._parent_code(req["code"]) else "move_chapter",
                        req,
                        title_match,
                        severity=severity,
                        source_type=source_type,
                        skippable=skippable,
                        payload={
                            "from_code": title_match["code"],
                            "required_code": req["code"],
                            "required_parent_code": self._parent_code(req["code"]),
                        },
                    )
                )
                continue

            if matched is None:
                suggestions.append(
                    self._suggestion(
                        "add_chapter",
                        req,
                        None,
                        severity=severity,
                        source_type=source_type,
                        skippable=skippable,
                        payload={"required_parent_code": self._parent_code(req["code"])},
                    )
                )

        for chapter in chapters:
            if chapter["id"] not in matched_chapter_ids and not self._has_similar_requirement(chapter, requirements):
                suggestions.append(
                    self._suggestion(
                        "disable_chapter",
                        {"code": None, "title": None, "source_type": "manual"},
                        chapter,
                        severity="low",
                        source_type="manual",
                        skippable=True,
                        payload={"chapter_code": chapter["code"], "chapter_title": chapter["title"]},
                    )
                )

        suggestions.extend(self._split_suggestions(requirements, chapters))
        suggestions.extend(self._merge_suggestions(requirements, chapters))
        return self._dedupe(suggestions)

    def validate_apply_selection(
        self,
        suggestions: list[DirectoryReconciliationSuggestion],
        *,
        skipped_suggestion_ids: list[str],
        not_applicable_reasons: dict[str, str],
    ) -> None:
        skipped = set(skipped_suggestion_ids)
        for suggestion in suggestions:
            if suggestion.id not in skipped:
                continue
            if suggestion.source_type == "tender_addendum" and suggestion.severity == "critical":
                reason = (not_applicable_reasons.get(suggestion.id) or "").strip()
                if not reason:
                    raise ValueError("critical tender_addendum suggestion requires explicit not_applicable reason")

    def summary(self, suggestions: list[DirectoryReconciliationSuggestion]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for item in suggestions:
            counts[item.severity] = counts.get(item.severity, 0) + 1
            by_type[item.suggestion_type] = by_type.get(item.suggestion_type, 0) + 1
        return {"counts_by_severity": counts, "counts_by_type": by_type, "critical": counts.get("critical", 0)}

    def _suggestion(
        self,
        suggestion_type: str,
        req: dict[str, Any],
        chapter: dict[str, Any] | None,
        *,
        severity: str,
        source_type: str,
        skippable: bool,
        payload: dict[str, Any],
    ) -> DirectoryReconciliationSuggestion:
        raw = f"{suggestion_type}:{req.get('code')}:{req.get('title')}:{chapter and chapter.get('id')}:{source_type}"
        return DirectoryReconciliationSuggestion(
            id=hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16],
            suggestion_type=suggestion_type,
            severity=severity,
            source_type=source_type,
            skippable=skippable,
            required_code=req.get("code"),
            required_title=req.get("title"),
            chapter_id=chapter.get("id") if chapter else None,
            payload=payload,
        )

    def _requirement_dict(self, item: Any) -> dict[str, Any]:
        data = dict(item if isinstance(item, dict) else getattr(item, "__dict__", {}))
        metadata = dict(data.get("source_metadata") or data.get("metadata_json") or {})
        return {
            **data,
            "code": str(data.get("directory_code") or data.get("chapter_code") or metadata.get("directory_code") or "").strip(),
            "title": str(data.get("title") or data.get("chapter_title") or data.get("requirement_text") or "").strip(),
            "source_type": data.get("source_type") or metadata.get("source_type") or "tender_document",
            "source_template_item_id": data.get("source_template_item_id") or metadata.get("source_template_item_id"),
            "mandatory": bool(data.get("mandatory") or data.get("is_hard_constraint") or data.get("is_veto")),
        }

    def _chapter_dict(self, item: Any) -> dict[str, Any]:
        data = dict(item) if isinstance(item, dict) else dict(getattr(item, "__dict__", {}) or {})

        def value(key: str, default: Any = None) -> Any:
            return data[key] if key in data else getattr(item, key, default)

        return {
            "id": value("id"),
            "parent_id": value("parent_id"),
            "source_template_item_id": value("source_template_item_id"),
            "code": str(value("chapter_code", "") or "").strip(),
            "title": str(value("chapter_title", "") or "").strip(),
            "sort_order": value("sort_order", 0),
        }

    def _is_directory_requirement(self, item: Any) -> bool:
        data = dict(item if isinstance(item, dict) else getattr(item, "__dict__", {}))
        return bool(data.get("directory_code") or data.get("chapter_code") or data.get("category") in {"directory", "format"})

    def _best_title_match(self, req: dict[str, Any], chapters: list[dict[str, Any]]) -> dict[str, Any] | None:
        req_norm = self._normalized(req["title"])
        if not req_norm:
            return None
        for chapter in chapters:
            chapter_norm = self._normalized(chapter["title"])
            if chapter_norm and (chapter_norm == req_norm or chapter_norm in req_norm or req_norm in chapter_norm):
                return chapter
        return None

    def _has_similar_requirement(self, chapter: dict[str, Any], requirements: list[dict[str, Any]]) -> bool:
        chapter_norm = self._normalized(chapter["title"])
        if not chapter_norm:
            return False
        return any(chapter_norm in self._normalized(req["title"]) or self._normalized(req["title"]) in chapter_norm for req in requirements)

    def _split_suggestions(self, requirements: list[dict[str, Any]], chapters: list[dict[str, Any]]) -> list[DirectoryReconciliationSuggestion]:
        results: list[DirectoryReconciliationSuggestion] = []
        for chapter in chapters:
            token = self._keyword(chapter["title"])
            if not token:
                continue
            matches = [req for req in requirements if token in self._normalized(req["title"]) and req["code"] != chapter["code"]]
            if len(matches) >= 2:
                results.append(
                    self._suggestion(
                        "split_chapter",
                        {"code": matches[0]["code"], "title": matches[0]["title"], "source_type": matches[0]["source_type"]},
                        chapter,
                        severity="medium",
                        source_type=matches[0]["source_type"],
                        skippable=True,
                        payload={"target_required_codes": [req["code"] for req in matches]},
                    )
                )
        return results

    def _merge_suggestions(self, requirements: list[dict[str, Any]], chapters: list[dict[str, Any]]) -> list[DirectoryReconciliationSuggestion]:
        results: list[DirectoryReconciliationSuggestion] = []
        for req in requirements:
            req_norm = self._normalized(req["title"])
            matched = [chapter for chapter in chapters if self._keyword(chapter["title"]) and self._keyword(chapter["title"]) in req_norm]
            if len(matched) >= 2:
                results.append(
                    self._suggestion(
                        "merge_chapter",
                        req,
                        matched[0],
                        severity="medium",
                        source_type=req["source_type"],
                        skippable=True,
                        payload={"merge_chapter_ids": [str(chapter["id"]) for chapter in matched]},
                    )
                )
        return results

    def _dedupe(self, suggestions: list[DirectoryReconciliationSuggestion]) -> list[DirectoryReconciliationSuggestion]:
        seen: set[tuple[str, str | None, UUID | None]] = set()
        result: list[DirectoryReconciliationSuggestion] = []
        for item in suggestions:
            key = (item.suggestion_type, item.required_code, item.chapter_id)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _parent_code(self, code: str | None) -> str | None:
        if not code or "." not in code:
            return None
        return code.rsplit(".", 1)[0]

    def _normalized(self, value: str | None) -> str:
        text = re.sub(r"[\s　、，。；;:：\-_/（）()《》\[\]]+", "", value or "")
        for suffix in ["文件", "章节", "内容"]:
            text = text.replace(suffix, "")
        return text.lower()

    def _keyword(self, value: str | None) -> str:
        norm = self._normalized(value)
        for token in ["质量", "安全", "施工", "资格", "签章", "盖章", "报价"]:
            if token in norm:
                return token
        return norm[:2]


__all__ = ["DirectoryReconciliationSuggestion", "TemplateDirectoryReconciliationService"]
