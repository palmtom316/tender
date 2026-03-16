"""Eval runner — evaluates extraction, retrieval, and generation quality.

Usage: python -m backend.tests.evals.eval_runner
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEST_SETS_DIR = Path(__file__).parent / "test_sets"


@dataclass
class EvalResult:
    test_name: str
    metric: str
    score: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    results: list[EvalResult] = field(default_factory=list)

    def add(self, result: EvalResult) -> None:
        self.results.append(result)

    def summary(self) -> dict[str, float]:
        by_metric: dict[str, list[float]] = {}
        for r in self.results:
            by_metric.setdefault(r.metric, []).append(r.score)
        return {k: sum(v) / len(v) for k, v in by_metric.items()}

    def to_json(self) -> str:
        return json.dumps(
            {
                "results": [
                    {"test": r.test_name, "metric": r.metric, "score": r.score, "details": r.details}
                    for r in self.results
                ],
                "summary": self.summary(),
            },
            indent=2,
            ensure_ascii=False,
        )


def load_test_set(name: str) -> list[dict]:
    """Load a test set from the test_sets directory."""
    path = TEST_SETS_DIR / f"{name}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def eval_fact_consistency(generated: str, expected_facts: list[str]) -> EvalResult:
    """Check if generated text contains expected facts."""
    found = sum(1 for f in expected_facts if f in generated)
    score = found / len(expected_facts) if expected_facts else 1.0
    return EvalResult(
        test_name="fact_consistency",
        metric="fact_consistency",
        score=score,
        details={"found": found, "total": len(expected_facts)},
    )


def eval_compliance_coverage(
    generated_sections: list[str], required_items: list[str]
) -> EvalResult:
    """Check if all required items are covered in generated sections."""
    all_text = " ".join(generated_sections)
    covered = sum(1 for item in required_items if item in all_text)
    score = covered / len(required_items) if required_items else 1.0
    return EvalResult(
        test_name="compliance_coverage",
        metric="compliance_coverage",
        score=score,
        details={"covered": covered, "total": len(required_items)},
    )


def eval_retrieval_hit_rate(
    queries: list[str], expected_hits: list[list[str]], actual_hits: list[list[str]]
) -> EvalResult:
    """Evaluate retrieval precision — what fraction of expected hits were found."""
    if not queries:
        return EvalResult(test_name="retrieval_hit_rate", metric="retrieval_hit_rate", score=1.0)
    total_expected = 0
    total_found = 0
    for expected, actual in zip(expected_hits, actual_hits):
        total_expected += len(expected)
        total_found += len(set(expected) & set(actual))
    score = total_found / total_expected if total_expected else 1.0
    return EvalResult(
        test_name="retrieval_hit_rate",
        metric="retrieval_hit_rate",
        score=score,
        details={"found": total_found, "total": total_expected},
    )


def run_eval() -> EvalReport:
    """Run all eval suites and return a report."""
    report = EvalReport()
    # Placeholder — will be populated as test sets are added
    return report


if __name__ == "__main__":
    report = run_eval()
    print(report.to_json())
