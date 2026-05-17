"""Fallback logic — primary model → fallback model on failure."""

from __future__ import annotations

import logging
import ipaddress
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

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
    finish_reason: str | None = None
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    extra_body: dict[str, Any] | None = None


def _read_field(value: Any, field: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(field, default)
    return getattr(value, field, default)


def _extract_usage_metrics(usage: Any) -> tuple[int, int, int, int, int]:
    input_tokens = int(_read_field(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(_read_field(usage, "completion_tokens", 0) or 0)
    prompt_cache_hit_tokens = int(_read_field(usage, "prompt_cache_hit_tokens", 0) or 0)
    prompt_cache_miss_tokens = int(_read_field(usage, "prompt_cache_miss_tokens", 0) or 0)
    completion_tokens_details = _read_field(usage, "completion_tokens_details")
    reasoning_tokens = int(_read_field(completion_tokens_details, "reasoning_tokens", 0) or 0)
    return (
        input_tokens,
        output_tokens,
        prompt_cache_hit_tokens,
        prompt_cache_miss_tokens,
        reasoning_tokens,
    )


def _override_extra_body(override: Any | None) -> dict[str, Any] | None:
    if override is None:
        return None
    extra = getattr(override, "extra_body", None)
    if not extra:
        return None
    return dict(extra)


def _allowed_override_hosts(raw: str) -> set[str]:
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _is_public_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host.lower() != "localhost"
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


def _validate_provider_override(override: Any | None, *, settings: Any, label: str) -> None:
    if override is None:
        return
    if not getattr(settings, "allow_provider_overrides", True):
        raise ValueError("provider overrides are disabled")
    base_url = str(getattr(override, "base_url", "") or "")
    if not base_url:
        return
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{label} base_url is not allowed")
    host = parsed.hostname.lower()
    if not _is_public_host(host):
        raise ValueError(f"{label} base_url host is not allowed")
    allowed_hosts = _allowed_override_hosts(getattr(settings, "provider_override_allowed_hosts", ""))
    if allowed_hosts and host not in allowed_hosts:
        raise ValueError(f"{label} base_url host is not in allowlist")


def _thinking_enabled(extra_body: dict[str, Any] | None) -> bool:
    if not isinstance(extra_body, dict):
        return False
    thinking = extra_body.get("thinking")
    return isinstance(thinking, dict) and thinking.get("type") == "enabled"


def _sanitize_extra_body_for_thinking(extra_body: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extra_body:
        return None
    sanitized = dict(extra_body)
    if not _thinking_enabled(sanitized):
        sanitized.pop("reasoning_effort", None)
    if not sanitized:
        return None
    return sanitized


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
    _validate_provider_override(primary_override, settings=settings, label="primary_override")
    _validate_provider_override(fallback_override, settings=settings, label="fallback_override")
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
# Tender extraction and long-form technical bid subsections need v4-pro's
# reasoning quality for recall, structural fidelity, and continuation coherence;
# other tasks stay on flash.
_V4_PRO_ALLOWED_TASKS = frozenset(
    {
        "extract_tender_requirements",
        "extract_tender_facts",
        "extract_scoring_criteria",
        "generate_longform_subsection",
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
    primary_thinking_mode = profile.get("primary_thinking_mode")

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
        # Profile-declared thinking mode applies only to the primary attempt;
        # fallback runs use the cheaper model without reasoning.
        if attempt == 0 and primary_thinking_mode == "max" and "thinking" not in merged_extra:
            merged_extra["thinking"] = {"type": "enabled"}
        sanitized_extra = _sanitize_extra_body_for_thinking(merged_extra)
        thinking_enabled = _thinking_enabled(sanitized_extra)

        start = time.perf_counter()
        try:
            create_kwargs: dict[str, Any] = {
                "model": provider.model,
                "messages": messages,
                "max_tokens": effective_max_tokens,
            }
            if not thinking_enabled:
                create_kwargs["temperature"] = temperature
            if sanitized_extra:
                create_kwargs["extra_body"] = sanitized_extra
            if response_format:
                create_kwargs["response_format"] = response_format
            if stream:
                create_kwargs["stream"] = True
                create_kwargs["stream_options"] = {"include_usage": True}
            resp = client.chat.completions.create(**create_kwargs)

            if stream:
                content_parts: list[str] = []
                finish_reason: str | None = None
                input_tokens = 0
                output_tokens = 0
                prompt_cache_hit_tokens = 0
                prompt_cache_miss_tokens = 0
                reasoning_tokens = 0
                for event in resp:
                    usage = _read_field(event, "usage")
                    if usage is not None:
                        (
                            input_tokens,
                            output_tokens,
                            prompt_cache_hit_tokens,
                            prompt_cache_miss_tokens,
                            reasoning_tokens,
                        ) = _extract_usage_metrics(usage)
                    delta = event.choices[0].delta if event.choices else None
                    if delta and delta.content:
                        content_parts.append(delta.content)
                    if event.choices:
                        finish_reason = getattr(event.choices[0], "finish_reason", finish_reason)
                latency_ms = int((time.perf_counter() - start) * 1000)
                return CompletionResult(
                    content="".join(content_parts),
                    model=provider.model,
                    provider=provider.name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    used_fallback=attempt > 0,
                    finish_reason=finish_reason,
                    prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                    prompt_cache_miss_tokens=prompt_cache_miss_tokens,
                    reasoning_tokens=reasoning_tokens,
                )

            latency_ms = int((time.perf_counter() - start) * 1000)
            usage = resp.usage
            (
                input_tokens,
                output_tokens,
                prompt_cache_hit_tokens,
                prompt_cache_miss_tokens,
                reasoning_tokens,
            ) = _extract_usage_metrics(usage)
            finish_reason = getattr(resp.choices[0], "finish_reason", None) if resp.choices else None

            return CompletionResult(
                content=resp.choices[0].message.content or "",
                model=provider.model,
                provider=provider.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                used_fallback=attempt > 0,
                finish_reason=finish_reason,
                prompt_cache_hit_tokens=prompt_cache_hit_tokens,
                prompt_cache_miss_tokens=prompt_cache_miss_tokens,
                reasoning_tokens=reasoning_tokens,
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
