"""Fallback logic — primary model → fallback model on failure."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from tender_ai_gateway.core.config import get_settings
from tender_ai_gateway.task_profiles import TASK_PROFILES

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    latency_ms: int = 0
    used_fallback: bool = False


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str


def _get_providers(
    task_type: str,
    primary_override: Any | None = None,
    fallback_override: Any | None = None,
) -> tuple[ProviderConfig, ProviderConfig]:
    """Resolve primary and fallback provider configs for a task type.

    When override objects are provided (with base_url, api_key, model attrs),
    they take precedence over env-var / profile defaults.
    """
    settings = get_settings()
    profile = TASK_PROFILES.get(task_type, {})
    primary_model = profile.get("primary_model", settings.default_primary_model)
    fallback_model = profile.get("fallback_model", settings.default_fallback_model)

    if primary_override and primary_override.base_url and primary_override.api_key:
        primary = ProviderConfig(
            name="override-primary",
            base_url=primary_override.base_url,
            api_key=primary_override.api_key,
            model=primary_override.model or primary_model,
        )
    else:
        primary = ProviderConfig(
            name="deepseek",
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
            model=primary_model,
        )

    if fallback_override and fallback_override.base_url and fallback_override.api_key:
        fallback = ProviderConfig(
            name="override-fallback",
            base_url=fallback_override.base_url,
            api_key=fallback_override.api_key,
            model=fallback_override.model or fallback_model,
        )
    else:
        fallback = ProviderConfig(
            name="qwen",
            base_url=settings.qwen_base_url,
            api_key=settings.qwen_api_key,
            model=fallback_model,
        )

    return primary, fallback


def call_with_fallback(
    *,
    task_type: str,
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    primary_override: Any | None = None,
    fallback_override: Any | None = None,
) -> CompletionResult:
    """Call primary provider, fall back to secondary on failure."""
    settings = get_settings()
    primary, fallback = _get_providers(task_type, primary_override, fallback_override)

    for attempt, provider in enumerate([primary, fallback]):
        if not provider.api_key:
            logger.warning("skipping_provider_no_key", extra={"provider": provider.name})
            continue

        client = OpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url,
            timeout=settings.default_timeout,
            max_retries=settings.default_retry_count,
        )

        start = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=provider.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            usage = resp.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            return CompletionResult(
                content=resp.choices[0].message.content or "",
                model=provider.model,
                provider=provider.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                used_fallback=attempt > 0,
            )
        except Exception as exc:
            logger.exception(
                "provider_call_failed provider=%s model=%s error_type=%s error=%s",
                provider.name,
                provider.model,
                type(exc).__name__,
                exc,
            )
            if attempt == 0:
                logger.info("falling_back", extra={"to": fallback.name})
                continue
            raise

    raise RuntimeError("No provider available — both primary and fallback failed or unconfigured")
