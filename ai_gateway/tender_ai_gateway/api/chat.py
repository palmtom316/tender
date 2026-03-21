from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tender_ai_gateway.core.config import get_settings
from tender_ai_gateway.fallback import call_with_fallback
from tender_ai_gateway.token_tracker import tracker

router = APIRouter(prefix="/ai", tags=["chat"])


class ProviderOverride(BaseModel):
    base_url: str
    api_key: str
    model: str


class ChatRequest(BaseModel):
    task_type: str = Field(..., examples=["generate_section"])
    provider_hint: str | None = Field(default=None, examples=["deepseek"])
    model: str | None = Field(default=None, examples=["deepseek-chat"])
    credential_id: str | None = None
    messages: list[dict[str, str]]
    temperature: float = 0.3
    max_tokens: int = 4096
    primary_override: ProviderOverride | None = None
    fallback_override: ProviderOverride | None = None


class ChatResponse(BaseModel):
    task_type: str
    resolved_model: str
    resolved_provider: str
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    latency_ms: int = 0
    used_fallback: bool = False


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    has_override_keys = (
        (request.primary_override and request.primary_override.api_key)
        or (request.fallback_override and request.fallback_override.api_key)
    )

    # Check if any API key is configured
    if not has_override_keys and not settings.deepseek_api_key and not settings.qwen_api_key:
        # Return stub response when no keys configured (dev mode)
        return ChatResponse(
            task_type=request.task_type,
            resolved_model=request.model or settings.default_primary_model,
            resolved_provider="stub",
            content="[AI Gateway stub — no API keys configured]",
        )

    try:
        result = call_with_fallback(
            task_type=request.task_type,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            primary_override=request.primary_override,
            fallback_override=request.fallback_override,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"All providers failed: {exc}")

    tracker.record(
        task_type=request.task_type,
        model=result.model,
        provider=result.provider,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
    )

    return ChatResponse(
        task_type=request.task_type,
        resolved_model=result.model,
        resolved_provider=result.provider,
        content=result.content,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        estimated_cost=result.estimated_cost,
        latency_ms=result.latency_ms,
        used_fallback=result.used_fallback,
    )
