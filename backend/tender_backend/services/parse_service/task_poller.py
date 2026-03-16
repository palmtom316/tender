"""Task poller — polls MinerU parse status until completion or timeout."""

from __future__ import annotations

import asyncio

import structlog

from tender_backend.services.parse_service.mineru_client import MineruClient, MineruParseResult

logger = structlog.stdlib.get_logger(__name__)

DEFAULT_POLL_INTERVAL = 5.0  # seconds
DEFAULT_MAX_POLLS = 120  # ~10 min with 5s interval


async def poll_until_complete(
    client: MineruClient,
    job_id: str,
    *,
    interval: float = DEFAULT_POLL_INTERVAL,
    max_polls: int = DEFAULT_MAX_POLLS,
) -> MineruParseResult:
    """Poll MinerU until the parse job reaches a terminal state."""
    for attempt in range(1, max_polls + 1):
        result = await client.get_parse_status(job_id)
        logger.info(
            "poll_status",
            job_id=job_id,
            status=result.status,
            attempt=attempt,
        )
        if result.status in ("completed", "failed"):
            return result
        await asyncio.sleep(interval)

    raise TimeoutError(f"MinerU parse job {job_id} did not complete after {max_polls} polls")
