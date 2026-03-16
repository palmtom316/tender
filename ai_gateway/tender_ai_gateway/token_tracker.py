"""Token and cost tracking for AI calls."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (USD) — update as pricing changes
COST_PER_1M: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "qwen-max": {"input": 2.0, "output": 6.0},
}


@dataclass
class TokenRecord:
    task_type: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    latency_ms: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD based on token counts."""
    rates = COST_PER_1M.get(model, {"input": 1.0, "output": 2.0})
    cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    return round(cost, 6)


class TokenTracker:
    """In-memory token usage tracker. In production, persists to task_trace table."""

    def __init__(self) -> None:
        self._records: list[TokenRecord] = []

    def record(
        self,
        *,
        task_type: str,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> TokenRecord:
        cost = estimate_cost(model, input_tokens, output_tokens)
        rec = TokenRecord(
            task_type=task_type,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=cost,
            latency_ms=latency_ms,
        )
        self._records.append(rec)
        logger.info(
            "token_recorded",
            extra={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
            },
        )
        return rec

    def total_cost(self) -> float:
        return sum(r.estimated_cost for r in self._records)

    def total_tokens(self) -> dict[str, int]:
        return {
            "input": sum(r.input_tokens for r in self._records),
            "output": sum(r.output_tokens for r in self._records),
        }

    @property
    def records(self) -> list[TokenRecord]:
        return list(self._records)


# Singleton instance
tracker = TokenTracker()
