#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
from uuid import UUID

from psycopg import connect
from psycopg.rows import dict_row


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1))))
    return float(ordered[index])


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _fmt_number(value: float | int) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.1f}"


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _fmt_delta(left: float, right: float, *, pct: bool = False) -> str:
    delta = right - left
    if pct:
        return f"{delta * 100:+.1f}pp"
    return f"{delta:+,.1f}"


def _fmt_change_rate(left: float, right: float) -> str:
    if left == 0:
        return "n/a"
    return f"{((right - left) / left) * 100:+.1f}%"


def _load_run(conn, run_id: UUID) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT * FROM tender_ai_extraction_run WHERE id = %s",
            (run_id,),
        ).fetchone()
    if row is None:
        raise SystemExit(f"run not found: {run_id}")
    return dict(row)


def _load_batches(conn, run_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM tender_ai_extraction_batch WHERE run_id = %s ORDER BY source_file, batch_index",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _wall_clock_seconds(run: dict[str, Any]) -> float:
    started_at = run.get("started_at")
    finished_at = run.get("finished_at")
    if started_at is None or finished_at is None:
        return 0.0
    return max(0.0, (finished_at - started_at).total_seconds())


def _policy_of(batch: dict[str, Any]) -> str:
    metadata = batch.get("metadata_json") or {}
    return str(metadata.get("quality_policy") or "legacy")


def _strategy_of(run: dict[str, Any], batches: list[dict[str, Any]]) -> str:
    metadata = run.get("metadata_json") or {}
    strategy = metadata.get("strategy_version")
    if strategy:
        return str(strategy)
    for batch in batches:
        batch_metadata = batch.get("metadata_json") or {}
        if batch_metadata.get("strategy_version"):
            return str(batch_metadata["strategy_version"])
    return "legacy"


def _by_policy(batches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for batch in batches:
        grouped[_policy_of(batch)].append(batch)
    return dict(grouped)


def _policy_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    provider_latencies = [
        float((batch.get("metadata_json") or {}).get("provider_latency_ms") or batch.get("latency_ms") or 0)
        for batch in items
    ]
    queue_latencies = [
        float((batch.get("metadata_json") or {}).get("queue_to_start_ms") or 0)
        for batch in items
    ]
    persist_latencies = [
        float((batch.get("metadata_json") or {}).get("persist_latency_ms") or 0)
        for batch in items
    ]
    cache_ratios = [
        float((batch.get("metadata_json") or {}).get("prompt_cache_hit_ratio") or 0.0)
        for batch in items
    ]
    prefilter_drop_ratios = [
        _safe_div(
            float((batch.get("metadata_json") or {}).get("prefilter_dropped_chunks") or 0),
            float((batch.get("metadata_json") or {}).get("original_chunk_count") or 0),
        )
        for batch in items
        if float((batch.get("metadata_json") or {}).get("original_chunk_count") or 0) > 0
    ]
    output_to_max = [
        float((batch.get("metadata_json") or {}).get("output_tokens_to_max_ratio") or 0.0)
        for batch in items
    ]
    return {
        "count": len(items),
        "provider_latency_ms_p50": round(median(provider_latencies), 1) if provider_latencies else 0.0,
        "provider_latency_ms_p95": round(_percentile(provider_latencies, 95), 1),
        "queue_to_start_ms_p50": round(median(queue_latencies), 1) if queue_latencies else 0.0,
        "persist_latency_ms_p50": round(median(persist_latencies), 1) if persist_latencies else 0.0,
        "avg_prompt_cache_hit_ratio": round(sum(cache_ratios) / len(cache_ratios), 4) if cache_ratios else 0.0,
        "avg_prefilter_drop_ratio": round(sum(prefilter_drop_ratios) / len(prefilter_drop_ratios), 4)
        if prefilter_drop_ratios
        else 0.0,
        "avg_output_tokens_to_max_ratio": round(sum(output_to_max) / len(output_to_max), 4) if output_to_max else 0.0,
    }


def _batch_metrics(batches: list[dict[str, Any]]) -> dict[str, Any]:
    return {policy: _policy_metrics(items) for policy, items in sorted(_by_policy(batches).items())}


def _run_summary(run: dict[str, Any], batches: list[dict[str, Any]]) -> dict[str, Any]:
    failure_types = Counter(str(batch.get("error_type") or "") for batch in batches if batch.get("error_type"))
    review_count = sum(1 for batch in batches if batch.get("status") == "needs_review")
    empty_output_count = sum(1 for batch in batches if int(batch.get("extracted_requirements") or 0) == 0)
    metadata_ratios = [
        float((batch.get("metadata_json") or {}).get("prompt_cache_hit_ratio") or 0.0)
        for batch in batches
    ]
    prefilter_dropped = sum(int((batch.get("metadata_json") or {}).get("prefilter_dropped_chunks") or 0) for batch in batches)
    original_chunks = sum(int((batch.get("metadata_json") or {}).get("original_chunk_count") or 0) for batch in batches)
    candidate_chunks = sum(int((batch.get("metadata_json") or {}).get("candidate_chunk_count") or 0) for batch in batches)
    return {
        "strategy_version": _strategy_of(run, batches),
        "status": run.get("status"),
        "wall_clock_seconds": round(_wall_clock_seconds(run), 1),
        "total_batches": int(run.get("total_batches") or 0),
        "succeeded_batches": int(run.get("succeeded_batches") or 0),
        "failed_batches": int(run.get("failed_batches") or 0),
        "skipped_batches": int(run.get("skipped_batches") or 0),
        "extracted_requirements": int(run.get("extracted_requirements") or 0),
        "total_input_tokens": int(run.get("total_input_tokens") or 0),
        "total_output_tokens": int(run.get("total_output_tokens") or 0),
        "avg_prompt_cache_hit_ratio": round(sum(metadata_ratios) / len(metadata_ratios), 4) if metadata_ratios else 0.0,
        "needs_review_batches": review_count,
        "zero_requirement_batches": empty_output_count,
        "failure_types": dict(failure_types),
        "prefilter_original_chunks": original_chunks,
        "prefilter_candidate_chunks": candidate_chunks,
        "prefilter_dropped_chunks": prefilter_dropped,
        "prefilter_drop_ratio": round(_safe_div(prefilter_dropped, original_chunks), 4) if original_chunks else 0.0,
        "requirements_per_1k_input_tokens": round(
            _safe_div(float(run.get("extracted_requirements") or 0), float(run.get("total_input_tokens") or 0)) * 1000,
            2,
        ),
        "by_quality_policy": _batch_metrics(batches),
    }


def _summary_rows(left: dict[str, Any], right: dict[str, Any]) -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []
    metrics = [
        ("Strategy", str(left["strategy_version"]), str(right["strategy_version"]), "", ""),
        ("Status", str(left["status"]), str(right["status"]), "", ""),
        (
            "Wall Clock (s)",
            _fmt_number(left["wall_clock_seconds"]),
            _fmt_number(right["wall_clock_seconds"]),
            _fmt_delta(left["wall_clock_seconds"], right["wall_clock_seconds"]),
            _fmt_change_rate(left["wall_clock_seconds"], right["wall_clock_seconds"]),
        ),
        (
            "Extracted Requirements",
            _fmt_number(left["extracted_requirements"]),
            _fmt_number(right["extracted_requirements"]),
            _fmt_delta(left["extracted_requirements"], right["extracted_requirements"]),
            _fmt_change_rate(float(left["extracted_requirements"]), float(right["extracted_requirements"])),
        ),
        (
            "Input Tokens",
            _fmt_number(left["total_input_tokens"]),
            _fmt_number(right["total_input_tokens"]),
            _fmt_delta(left["total_input_tokens"], right["total_input_tokens"]),
            _fmt_change_rate(float(left["total_input_tokens"]), float(right["total_input_tokens"])),
        ),
        (
            "Output Tokens",
            _fmt_number(left["total_output_tokens"]),
            _fmt_number(right["total_output_tokens"]),
            _fmt_delta(left["total_output_tokens"], right["total_output_tokens"]),
            _fmt_change_rate(float(left["total_output_tokens"]), float(right["total_output_tokens"])),
        ),
        (
            "Avg Prompt Cache Hit Ratio",
            _fmt_pct(left["avg_prompt_cache_hit_ratio"]),
            _fmt_pct(right["avg_prompt_cache_hit_ratio"]),
            _fmt_delta(left["avg_prompt_cache_hit_ratio"], right["avg_prompt_cache_hit_ratio"], pct=True),
            _fmt_change_rate(left["avg_prompt_cache_hit_ratio"], right["avg_prompt_cache_hit_ratio"]),
        ),
        (
            "Needs Review Batches",
            _fmt_number(left["needs_review_batches"]),
            _fmt_number(right["needs_review_batches"]),
            _fmt_delta(left["needs_review_batches"], right["needs_review_batches"]),
            _fmt_change_rate(float(left["needs_review_batches"]), float(right["needs_review_batches"])),
        ),
        (
            "Zero Requirement Batches",
            _fmt_number(left["zero_requirement_batches"]),
            _fmt_number(right["zero_requirement_batches"]),
            _fmt_delta(left["zero_requirement_batches"], right["zero_requirement_batches"]),
            _fmt_change_rate(float(left["zero_requirement_batches"]), float(right["zero_requirement_batches"])),
        ),
        (
            "Prefilter Drop Ratio",
            _fmt_pct(left["prefilter_drop_ratio"]),
            _fmt_pct(right["prefilter_drop_ratio"]),
            _fmt_delta(left["prefilter_drop_ratio"], right["prefilter_drop_ratio"], pct=True),
            _fmt_change_rate(left["prefilter_drop_ratio"], right["prefilter_drop_ratio"]),
        ),
        (
            "Requirements / 1k Input Tokens",
            _fmt_number(left["requirements_per_1k_input_tokens"]),
            _fmt_number(right["requirements_per_1k_input_tokens"]),
            _fmt_delta(left["requirements_per_1k_input_tokens"], right["requirements_per_1k_input_tokens"]),
            _fmt_change_rate(left["requirements_per_1k_input_tokens"], right["requirements_per_1k_input_tokens"]),
        ),
    ]
    rows.extend(metrics)
    return rows


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_No data_"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _policy_rows(left: dict[str, Any], right: dict[str, Any]) -> list[list[str]]:
    policies = sorted(set(left["by_quality_policy"]) | set(right["by_quality_policy"]))
    rows: list[list[str]] = []
    for policy in policies:
        left_metrics = left["by_quality_policy"].get(policy, {})
        right_metrics = right["by_quality_policy"].get(policy, {})
        rows.append(
            [
                policy,
                str(left_metrics.get("count", 0)),
                str(right_metrics.get("count", 0)),
                _fmt_number(left_metrics.get("provider_latency_ms_p50", 0.0)),
                _fmt_number(right_metrics.get("provider_latency_ms_p50", 0.0)),
                _fmt_number(left_metrics.get("provider_latency_ms_p95", 0.0)),
                _fmt_number(right_metrics.get("provider_latency_ms_p95", 0.0)),
                _fmt_pct(float(left_metrics.get("avg_prompt_cache_hit_ratio", 0.0))),
                _fmt_pct(float(right_metrics.get("avg_prompt_cache_hit_ratio", 0.0))),
                _fmt_pct(float(left_metrics.get("avg_prefilter_drop_ratio", 0.0))),
                _fmt_pct(float(right_metrics.get("avg_prefilter_drop_ratio", 0.0))),
            ]
        )
    return rows


def _failure_rows(left: dict[str, Any], right: dict[str, Any]) -> list[list[str]]:
    keys = sorted(set(left["failure_types"]) | set(right["failure_types"]))
    return [[key, str(left["failure_types"].get(key, 0)), str(right["failure_types"].get(key, 0))] for key in keys]


def _render_markdown(left_id: UUID, left: dict[str, Any], right_id: UUID, right: dict[str, Any]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary_table = _markdown_table(
        ["Metric", "Left", "Right", "Delta", "Change"],
        [[a, b, c, d, e] for a, b, c, d, e in _summary_rows(left, right)],
    )
    policy_table = _markdown_table(
        [
            "Quality Policy",
            "Left Count",
            "Right Count",
            "Left P50 Provider ms",
            "Right P50 Provider ms",
            "Left P95 Provider ms",
            "Right P95 Provider ms",
            "Left Cache Hit",
            "Right Cache Hit",
            "Left Prefilter Drop",
            "Right Prefilter Drop",
        ],
        _policy_rows(left, right),
    )
    failure_table = _markdown_table(
        ["Failure Type", "Left Count", "Right Count"],
        _failure_rows(left, right),
    )
    return "\n".join(
        [
            "# Tender AI Extraction Baseline Compare",
            "",
            f"- Generated at: {now}",
            f"- Left run: `{left_id}`",
            f"- Right run: `{right_id}`",
            "",
            "## Summary",
            "",
            summary_table,
            "",
            "## By Quality Policy",
            "",
            policy_table,
            "",
            "## Failure Distribution",
            "",
            failure_table,
            "",
            "## JSON Detail",
            "",
            "```json",
            json.dumps({"left": left, "right": right}, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two tender AI extraction runs.")
    parser.add_argument("left_run_id")
    parser.add_argument("right_run_id")
    parser.add_argument("--out", default="", help="Optional output markdown path")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    left_run_id = UUID(args.left_run_id)
    right_run_id = UUID(args.right_run_id)

    with connect(database_url) as conn:
        left_run = _load_run(conn, left_run_id)
        right_run = _load_run(conn, right_run_id)
        left_batches = _load_batches(conn, left_run_id)
        right_batches = _load_batches(conn, right_run_id)

    left_summary = _run_summary(left_run, left_batches)
    right_summary = _run_summary(right_run, right_batches)
    markdown = _render_markdown(left_run_id, left_summary, right_run_id, right_summary)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"wrote {out_path}")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
