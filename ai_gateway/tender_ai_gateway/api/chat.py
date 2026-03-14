from fastapi import APIRouter
from pydantic import BaseModel, Field

from tender_ai_gateway.core.config import get_settings

router = APIRouter(prefix="/ai", tags=["chat"])


class ChatRequest(BaseModel):
    task_type: str = Field(..., examples=["generate_section"])
    provider_hint: str | None = Field(default=None, examples=["ccswitch-openai"])
    model: str | None = Field(default=None, examples=["deepseek-chat"])
    credential_id: str | None = None
    messages: list[dict[str, str]]


class ChatResponse(BaseModel):
    task_type: str
    resolved_model: str
    resolved_provider: str
    credential_mode: str
    accepted: bool = True


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    return ChatResponse(
        task_type=request.task_type,
        resolved_model=request.model or settings.default_primary_model,
        resolved_provider=request.provider_hint or "deepseek-primary",
        credential_mode="server-proxy",
    )
