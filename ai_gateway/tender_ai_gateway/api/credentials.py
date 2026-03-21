from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/credentials", tags=["credentials"])


class CredentialCreateRequest(BaseModel):
    provider: str = Field(..., examples=["deepseek", "ccswitch-openai"])
    display_name: str = Field(..., examples=["personal-debug-key"])
    api_key: str = Field(..., min_length=8)


class CredentialCreateResponse(BaseModel):
    credential_id: str
    provider: str
    display_name: str
    mode: str = "server-proxy-byok"


@router.post("", response_model=CredentialCreateResponse)
async def create_credential(request: CredentialCreateRequest) -> CredentialCreateResponse:
    # Phase 1 stub: credentials are not persisted yet. This endpoint defines the
    # server-proxy BYOK contract so the frontend never talks to providers directly.
    return CredentialCreateResponse(
        credential_id=str(uuid4()),
        provider=request.provider,
        display_name=request.display_name,
    )
