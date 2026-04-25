"""Executable parse-skill plugin hooks for the standard parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


BLOCKING_FAILURE_HOOKS = {
    "preflight_parse_asset",
    "after_validation",
}


@dataclass
class ParseSkillContext:
    standard: dict | None
    document_id: str
    document_asset: Any
    raw_sections: list[dict]
    tables: list[dict]
    artifacts_dir: str | None = None
    clauses: list[dict] = field(default_factory=list)
    validation: Any | None = None


@dataclass
class ParseSkillResult:
    status: str
    messages: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    raw_sections: list[dict] | None = None
    tables: list[dict] | None = None
    document_asset: Any | None = None


@dataclass(frozen=True)
class ExecutedParseSkill:
    skill_name: str
    hook: str
    status: str
    blocking: bool
    messages: list[str]
    metrics: dict[str, Any]


class ParseSkillPlugin(Protocol):
    name: str
    hooks: tuple[str, ...]

    def run(self, hook: str, context: ParseSkillContext) -> ParseSkillResult:
        ...


class MineruStandardBundlePlugin:
    name = "mineru-standard-bundle"
    hooks = ("preflight_parse_asset", "cleanup_parse_asset")

    def run(self, hook: str, context: ParseSkillContext) -> ParseSkillResult:
        anchored_sections = sum(
            1 for section in context.raw_sections if section.get("page_start") is not None
        )
        total_sections = len(context.raw_sections)
        section_page_coverage_ratio = (
            round(anchored_sections / total_sections, 3) if total_sections else 0.0
        )
        metrics = {
            "raw_section_count": total_sections,
            "anchored_section_count": anchored_sections,
            "section_page_coverage_ratio": section_page_coverage_ratio,
            "table_count": len(context.tables),
        }
        if hook == "preflight_parse_asset" and total_sections == 0:
            return ParseSkillResult(
                status="fail",
                messages=["no parseable sections in MinerU asset"],
                metrics=metrics,
            )
        return ParseSkillResult(status="pass", metrics=metrics)


class StandardParseRecoveryPlugin:
    name = "standard-parse-recovery"
    hooks = ("after_validation", "recovery_diagnostics")

    def run(self, hook: str, context: ParseSkillContext) -> ParseSkillResult:
        issues = list(getattr(context.validation, "issues", []) or [])
        severity_counts: dict[str, int] = {}
        for issue in issues:
            severity = str(getattr(issue, "severity", "warning") or "warning")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        metrics = {
            "validation_issue_count": len(issues),
            "validation_severity_counts": severity_counts,
        }
        if hook == "after_validation" and severity_counts.get("error", 0) > 0:
            return ParseSkillResult(
                status="fail",
                messages=["validation contains blocking errors"],
                metrics=metrics,
            )
        return ParseSkillResult(status="pass", metrics=metrics)


def default_parse_skill_plugins() -> list[ParseSkillPlugin]:
    return [
        MineruStandardBundlePlugin(),
        StandardParseRecoveryPlugin(),
    ]


def _is_blocking_failure(hook: str, result: ParseSkillResult) -> bool:
    return result.status == "fail" and hook in BLOCKING_FAILURE_HOOKS


def run_parse_skill_hooks(
    *,
    hook: str,
    context: ParseSkillContext,
    plugins: list[ParseSkillPlugin],
    active_skill_names: set[str],
) -> list[ExecutedParseSkill]:
    """Run active parse-skill plugins for a hook and return execution summaries."""
    executed: list[ExecutedParseSkill] = []

    for plugin in plugins:
        if plugin.name not in active_skill_names:
            continue
        if hook not in plugin.hooks:
            continue

        result = plugin.run(hook, context)
        executed.append(
            ExecutedParseSkill(
                skill_name=plugin.name,
                hook=hook,
                status=result.status,
                blocking=_is_blocking_failure(hook, result),
                messages=list(result.messages),
                metrics=dict(result.metrics),
            )
        )

    return executed
