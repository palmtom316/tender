from __future__ import annotations

from tender_backend.services.skill_catalog import default_skill_specs


def test_default_skill_specs_expose_executable_parse_plugin_metadata() -> None:
    specs = {spec.skill_name: spec for spec in default_skill_specs()}

    mineru = specs["mineru-standard-bundle"]
    recovery = specs["standard-parse-recovery"]

    assert mineru.skill_type == "parse_plugin"
    assert mineru.hook_names == ["preflight_parse_asset", "cleanup_parse_asset"]
    assert recovery.skill_type == "parse_plugin"
    assert recovery.hook_names == ["after_validation", "recovery_diagnostics"]


def test_default_skill_specs_keep_workflows_and_docs_separate() -> None:
    specs = default_skill_specs()

    assert {spec.skill_type for spec in specs}.issuperset({"workflow", "parse_plugin"})
    assert all(
        spec.skill_type in {"workflow", "documentation", "parse_plugin"}
        for spec in specs
    )
