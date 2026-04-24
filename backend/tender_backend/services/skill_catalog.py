from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tender_backend.workflows.export_bid  # noqa: F401
import tender_backend.workflows.generate_section  # noqa: F401
import tender_backend.workflows.review_section  # noqa: F401
import tender_backend.workflows.standard_ingestion  # noqa: F401
import tender_backend.workflows.tender_ingestion  # noqa: F401
from tender_backend.workflows.registry import get_workflow, list_workflows


@dataclass(frozen=True)
class SkillSpec:
    skill_name: str
    description: str
    tool_names: list[str]
    version: int = 1
    active: bool = True


_FALLBACK_DOC_SKILLS: tuple[SkillSpec, ...] = (
    SkillSpec(
        skill_name="mineru-standard-bundle",
        description=(
            "Use when working in the tender repository with MinerU 2.7.x hybrid/vlm "
            "standard-document outputs and you need deterministic bundle generation, "
            "quality evaluation, cleanup, or cross-standard comparison from local pdf, md, and json files."
        ),
        tool_names=["run_mineru_standard_bundle"],
    ),
    SkillSpec(
        skill_name="standard-parse-recovery",
        description=(
            "Use when standard document parsing quality regresses in this repo, especially "
            "for MinerU parse drift, table provenance/page anchor issues, AI scope timeout "
            "failures, or validation-count regressions in tender backend norm_service."
        ),
        tool_names=[],
    ),
)


def _extract_docstring_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if not line.startswith('"""') and not line.startswith("#"):
            return line
    return ""


def _workflow_skill_specs() -> list[SkillSpec]:
    specs: list[SkillSpec] = []
    for workflow_name in sorted(list_workflows()):
        workflow_cls = get_workflow(workflow_name)
        workflow = workflow_cls()
        description = _extract_docstring_summary(workflow_cls.__doc__ or "") or workflow_name
        specs.append(
            SkillSpec(
                skill_name=workflow_name,
                description=description,
                tool_names=[step.name for step in workflow.steps],
            )
        )
    return specs


def _parse_skill_frontmatter(skill_path: Path) -> tuple[str, str]:
    text = skill_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return skill_path.parent.name, _extract_docstring_summary(text)

    metadata: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")

    return (
        metadata.get("name") or skill_path.parent.name,
        metadata.get("description") or _extract_docstring_summary(text),
    )


def _doc_skill_tool_names(skill_dir: Path) -> list[str]:
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.exists():
        return []
    return sorted(
        path.stem
        for path in scripts_dir.glob("*.py")
        if path.is_file() and path.stem != "__init__"
    )


def _doc_skill_specs() -> list[SkillSpec]:
    root = Path(__file__).resolve().parents[3] / "docs" / "skills"
    if not root.exists():
        return []

    specs: list[SkillSpec] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        skill_name, description = _parse_skill_frontmatter(skill_md)
        specs.append(
            SkillSpec(
                skill_name=skill_name,
                description=description,
                tool_names=_doc_skill_tool_names(skill_md.parent),
            )
        )
    return specs


def default_skill_specs() -> list[SkillSpec]:
    seen: set[str] = set()
    specs: list[SkillSpec] = []
    for spec in [*_workflow_skill_specs(), *_doc_skill_specs(), *_FALLBACK_DOC_SKILLS]:
        if spec.skill_name in seen:
            continue
        seen.add(spec.skill_name)
        specs.append(spec)
    return specs
