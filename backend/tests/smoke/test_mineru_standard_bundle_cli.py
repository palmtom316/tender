from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _write_sample(tmp_path: Path, *, name: str) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / f"{name}.pdf"
    md_path = tmp_path / f"{name}.md"
    json_path = tmp_path / f"{name}.json"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")
    md_path.write_text("1 总则\n这是正文内容", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "_backend": "hybrid",
                "_version_name": "2.7.6",
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "para_blocks": [
                            {"type": "title", "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}]},
                            {"type": "text", "lines": [{"spans": [{"content": "这是正文内容", "type": "text"}]}]},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pdf_path, md_path, json_path


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / "docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py"), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_evaluate_writes_base_outputs(tmp_path: Path) -> None:
    pdf_path, md_path, json_path = _write_sample(tmp_path, name="gb50150")
    output_dir = tmp_path / "out"
    result = _run_cli(
        [
            "evaluate",
            "--name",
            "GB50150-2016",
            "--pdf",
            str(pdf_path),
            "--md",
            str(md_path),
            "--json",
            str(json_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "raw-payload.json").exists()
    assert (output_dir / "system-bundle.json").exists()
    assert (output_dir / "summary.json").exists()


def test_cli_clean_writes_cleaned_outputs(tmp_path: Path) -> None:
    pdf_path, md_path, json_path = _write_sample(tmp_path, name="gb50150")
    output_dir = tmp_path / "out"
    result = _run_cli(
        [
            "clean",
            "--name",
            "GB50150-2016",
            "--pdf",
            str(pdf_path),
            "--md",
            str(md_path),
            "--json",
            str(json_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "cleaned-system-bundle.json").exists()
    assert (output_dir / "cleaned-summary.json").exists()


def test_cli_compare_writes_json_and_markdown_reports(tmp_path: Path) -> None:
    left = _write_sample(tmp_path / "left", name="gb50147")
    right = _write_sample(tmp_path / "right", name="gb50150")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {"name": "GB50147-2010", "pdf": str(left[0]), "md": str(left[1]), "json": str(left[2])},
                {"name": "GB50150-2016", "pdf": str(right[0]), "md": str(right[1]), "json": str(right[2])},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "compare"
    result = _run_cli(
        [
            "compare",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "compare-summary.json").exists()
    assert (output_dir / "compare-report.md").exists()
