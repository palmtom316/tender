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
    extra_body: dict[str, Any] | None = None


def _override_extra_body(override: Any | None) -> dict[str, Any] | None:
    if override is None:
        return None
    extra = getattr(override, "extra_body", None)
    if not extra:
        return None
    return dict(extra)


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
            extra_body=_override_extra_body(primary_override),
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
            extra_body=_override_extra_body(fallback_override),
        )
    else:
        fallback = ProviderConfig(
            name="qwen",
            base_url=settings.qwen_base_url,
            api_key=settings.qwen_api_key,
            model=fallback_model,
        )

    return primary, fallback


# Tasks that may use deepseek-v4-pro despite the global cost-control guard.
# Tender extraction needs v4-pro's reasoning quality for recall and structural
# fidelity; everything else stays on flash.
_V4_PRO_ALLOWED_TASKS = frozenset(
    {
        "extract_tender_requirements",
        "extract_tender_facts",
        "extract_scoring_criteria",
    }
)


def _reject_disallowed_model(model: str, task_type: str) -> None:
    normalized = str(model or "").strip().lower()
    if normalized in {"deepseek-v4-pro", "deepseek/deepseek-v4-pro"}:
        if task_type in _V4_PRO_ALLOWED_TASKS:
            return
        raise ValueError(
            f"deepseek-v4-pro is disabled for task '{task_type}' (cost control); use deepseek-v4-flash"
        )


def call_with_fallback(
    *,
    task_type: str,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int | None = None,
    primary_override: Any | None = None,
    fallback_override: Any | None = None,
    extra_body: dict[str, Any] | None = None,
    response_format: dict[str, Any] | None = None,
    stream: bool = False,
) -> CompletionResult:
    """Call primary provider, fall back to secondary on failure.

    `extra_body` (and any per-override `extra_body`) is forwarded to the OpenAI
    SDK so model-specific fields like `reasoning_effort` reach the provider.
    """
    settings = get_settings()
    profile = TASK_PROFILES.get(task_type, {})
    primary, fallback = _get_providers(task_type, primary_override, fallback_override)
    timeout = profile.get("timeout", settings.default_timeout)
    max_retries = profile.get("max_retries", settings.default_retry_count)
    effective_max_tokens = max_tokens if max_tokens is not None else profile.get("max_tokens", 4096)

    for attempt, provider in enumerate([primary, fallback]):
        if not provider.api_key:
            logger.warning("skipping_provider_no_key", extra={"provider": provider.name})
            continue
        _reject_disallowed_model(provider.model, task_type)

        client = OpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

        merged_extra: dict[str, Any] = {}
        if extra_body:
            merged_extra.update(extra_body)
        if provider.extra_body:
            merged_extra.update(provider.extra_body)

        start = time.perf_counter()
        try:
            create_kwargs: dict[str, Any] = {
                "model": provider.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": effective_max_tokens,
            }
            if merged_extra:
                create_kwargs["extra_body"] = merged_extra
            if response_format:
                create_kwargs["response_format"] = response_format
            if stream:
                create_kwargs["stream"] = True
            resp = client.chat.completions.create(**create_kwargs)
            latency_ms = int((time.perf_counter() - start) * 1000)

            if stream:
                content_parts: list[str] = []
                for event in resp:
                    delta = event.choices[0].delta if event.choices else None
                    if delta and delta.content:
                        content_parts.append(delta.content)
                return CompletionResult(
                    content="".join(content_parts),
                    model=provider.model,
                    provider=provider.name,
                    latency_ms=latency_ms,
                    used_fallback=attempt > 0,
                )

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
