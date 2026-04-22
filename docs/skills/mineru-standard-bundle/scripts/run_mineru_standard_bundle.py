from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))

from tender_backend.services.norm_service.mineru_standard_bundle import (  # noqa: E402
    StandardSampleInput,
    build_standard_bundle,
    clean_standard_bundle,
    compare_standard_summaries,
    evaluate_standard_bundle,
    write_bundle_outputs,
    write_compare_report,
)


def _sample_from_args(args: argparse.Namespace) -> StandardSampleInput:
    return StandardSampleInput(
        name=args.name,
        pdf_path=Path(args.pdf),
        md_path=Path(args.md),
        json_path=Path(args.json),
    )


def cmd_evaluate(args: argparse.Namespace) -> int:
    sample = _sample_from_args(args)
    bundle = build_standard_bundle(sample)
    summary = evaluate_standard_bundle(bundle)
    write_bundle_outputs(Path(args.output_dir), bundle=bundle, summary=summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    sample = _sample_from_args(args)
    bundle = build_standard_bundle(sample)
    summary = evaluate_standard_bundle(bundle)
    cleaned = clean_standard_bundle(bundle)
    cleaned_summary = evaluate_standard_bundle(cleaned)
    output_dir = Path(args.output_dir)
    write_bundle_outputs(output_dir, bundle=bundle, summary=summary)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cleaned-system-bundle.json").write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "cleaned-summary.json").write_text(
        json.dumps(cleaned_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(cleaned_summary, ensure_ascii=False, indent=2))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    summaries = []
    for item in manifest:
        sample = StandardSampleInput(
            name=item["name"],
            pdf_path=Path(item["pdf"]),
            md_path=Path(item["md"]),
            json_path=Path(item["json"]),
        )
        bundle = build_standard_bundle(sample)
        summaries.append(evaluate_standard_bundle(bundle))
    comparison = compare_standard_summaries(summaries)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "compare-summary.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_compare_report(output_dir, comparison)
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--name", required=True)
    evaluate.add_argument("--pdf", required=True)
    evaluate.add_argument("--md", required=True)
    evaluate.add_argument("--json", required=True)
    evaluate.add_argument("--output-dir", required=True)
    evaluate.set_defaults(func=cmd_evaluate)

    clean = subparsers.add_parser("clean")
    clean.add_argument("--name", required=True)
    clean.add_argument("--pdf", required=True)
    clean.add_argument("--md", required=True)
    clean.add_argument("--json", required=True)
    clean.add_argument("--output-dir", required=True)
    clean.set_defaults(func=cmd_clean)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--manifest", required=True)
    compare.add_argument("--output-dir", required=True)
    compare.set_defaults(func=cmd_compare)
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))
